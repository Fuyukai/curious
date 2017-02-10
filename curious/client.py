import inspect
import typing
import logging

import curio
import multidict
from cuiows.exc import WebsocketClosedError
from curio.task import Task

from curious.dataclasses.guild import Guild
from curious.dataclasses.invite import Invite
from curious.dataclasses.status import Game, Status
from curious.dataclasses.user import User
from curious.dataclasses.webhook import Webhook
from curious.event import EventContext
from curious.http.httpclient import HTTPClient
from curious.util import _traverse_stack_for, base64ify

AUTOSHARD = object()


class AppInfo(object):
    """
    Represents the application info for a
    """
    def __init__(self, client: 'Client', **kwargs):
        #: The client ID of this application.
        self.client_id = int(kwargs.pop("id", 0))

        #: The owner of this application.
        self.owner = User(client, **kwargs.pop("owner"))

        #: The description of this application.
        self.description = kwargs.pop("description")

        #: Is this bot public?
        self.public = kwargs.pop("public", None)

        #: The icon hash for this bot.
        self._icon_hash = kwargs.pop("icon", None)

    @property
    def icon_url(self):
        """
        :return: The icon url for this bot.
        """
        if self._icon_hash is None:
            return None

        return "https://cdn.discordapp.com/app-icons/{}/{}.jpg".format(self.client_id, self._icon_hash)


class Client(object):
    """
    The main client class. This is used to interact with Discord.

    When creating a client object, you can either pass a token explicitly, or pass in in the :meth:`start` call or
    similar.

    .. code:: python

        bot = Client("'a'")  # pass explicitly
        bot.run("'b'")  # or pass to the run call.
    """
    def __init__(self, token: str = None, *,
                 state_klass: type = None):
        """
        :param token: The current token for this bot.
            This can be passed as None and can be initialized later.
        :param state_klass: The class to construct the connection state from.
        """
        #: The mapping of `shard_id -> gateway` objects.
        self._gateways = {}  # type: typing.Dict[int, Gateway]

        #: The number of shards this client has.
        self.shard_count = 0

        #: The token for the bot.
        self._token = token

        #: The current connection state for the bot.
        if state_klass is None:
            from curious.state import State
            state_klass = State
        self.state = state_klass(self)

        #: The current event storage.
        self.events = multidict.MultiDict()

        #: The current "temporary" listener storage.
        #: Temporary listeners are events that listen, and if they return True the listener is remove.
        #: They are used in the HTTP method by `wait=`, for example.
        self._temporary_listeners = multidict.MultiDict()

        #: The :class:`HTTPClient` used for this bot.
        self.http = None  # type: HTTPClient

        #: The cached gateway URL.
        self._gw_url = None  # type: str

        #: The application info for this bot.
        #: Instance of :class:`AppInfo`.
        self.application_info = None  # type: AppInfo

        #: The logger for this bot.
        self._logger = logging.getLogger("curious.client")

        # Scan the dict of this object, to check for all events registered under it.
        # This is useful, for example, for subclasses.
        for name, obb in self.__class__.__dict__.items():
            if name.startswith("on_") and inspect.iscoroutinefunction(obb):
                self.add_event(name[3:], getattr(self, name))

    @property
    def user(self) -> User:
        """
        :return: The :class:`User` that this client is logged in as.
        """
        return self.state._user

    @property
    def guilds(self) -> typing.Mapping[int, Guild]:
        """
        :return: A list of :class:`Guild` that this client can see.
        """
        return self.state.guilds

    @property
    def invite_url(self):
        """
        :return: The invite URL for this bot.
        """
        return "https://discordapp.com/oauth2/authorize?client_id={}&scope=bot".format(self.application_info.client_id)

    async def get_gateway_url(self):
        if self._gw_url:
            return self._gw_url

        self._gw_url = await self.http.get_gateway_url()
        return self._gw_url

    async def get_shard_count(self):
        gw, shards = await self.http.get_shard_count()
        self._gw_url = gw

        return shards

    def guilds_for(self, shard_id: int) -> typing.Iterable[Guild]:
        """
        Gets the guilds for this shard.

        :param shard_id: The shard ID to get guilds from.
        :return: A list of :class:`Guild` that client can see on the specified shard.
        """
        return self.state.guilds_for_shard(shard_id)

    # Events
    def add_event(self, name: str, func):
        """
        Add an event to the internal registry of events.

        :param name: The event name to register under.
        :param func: The function to add.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Event must be a coroutine function")

        self.events.add(name, func)

    def add_listener(self, name: str, func):
        """
        Adds a temporary listener.

        :param name: The name of the event to listen under.
        :param func: The callable to call.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Listener must be a coroutine function")

        self._temporary_listeners.add(name, func)

    def remove_event(self, name: str, func):
        """
        Removes a function event.

        :param name: The name the event is registered under/.
        :param func: The function to remove.
        """
        a = self.events.getall(name)
        if func in a:
            a.remove(func)

        self.events.pop(name)
        for item in a:
            self.events.add(name, item)

    def event(self, func):
        """
        Marks a function as an event.

        This will copy it to the events dictionary, where it will be used as an event later on.

        :param func: The function to mark as an event.
            This can also be a string, which will allow you to customize the event added.
        :return: The unmodified function.
        """
        if isinstance(func, str):
            event = func

            def _inner(func):
                self.add_event(event, func)
                return func

            return _inner

        if not func.__name__.startswith("on_"):
            raise ValueError("Events must start with on_")

        event = func.__name__[3:]
        self.add_event(event, func)

        return func

    async def _error_wrapper(self, func, *args, **kwargs):
        try:
            await func(*args, **kwargs)
        except Exception as e:
            self._logger.exception("Unhandled exception in {}!".format(func.__name__))

    async def _temporary_wrapper(self, event, listener, *args, **kwargs):
        try:
            result = await listener(*args, **kwargs)
        except Exception as e:
            self._logger.exception("Unhandled exception in {}!".format(listener.__name__))
            return
        if result is True:
            # Complex removal bullshit
            try:
                items = self._temporary_listeners.getall(event)
            except KeyError:
                # early removal done already, ignore
                return

            try:
                items.remove(listener)
            except ValueError:
                # race condition bullshit
                return
            # remove all keys
            self._temporary_listeners.pop(event)

            for i in items:
                # re-add all new items
                self._temporary_listeners.add(event, i)

    def remove_listener_early(self, event, listener):
        """
        Removes a listener early.

        :param event: The event to remove from.
        :param listener: The listener to remove.
        """
        all = self._temporary_listeners.getall(event)
        if listener in all:
            all.remove(listener)

        self._temporary_listeners.pop(event)
        for i in all:
            self._temporary_listeners.add(event, i)

    async def fire_event(self, event_name: str, *args, **kwargs) -> typing.List[Task]:
        """
        Fires an event to run.

        This will wrap the events in Tasks and return a list of them.

        :param event_name: The event name to fire.
        :return: A :class:`list` of :class:`curio.task.Task` representing the events.
        """
        gateway = kwargs.pop("gateway")

        if "ctx" not in kwargs:
            ctx = EventContext(self, gateway.shard_id)
        else:
            ctx = kwargs.pop("ctx")

        coros = self.events.getall(event_name, [])

        temporary_listeners = self._temporary_listeners.getall(event_name, [])

        if not coros and not temporary_listeners:
            return

        self._logger.debug(
            "Dispatching event {} to {} listeners"
            " on shard {}".format(event_name, len(coros) + len(temporary_listeners), gateway.shard_id)
        )

        tasks = []
        for event in coros.copy():
            tasks.append(await curio.spawn(self._error_wrapper(event, ctx, *args, **kwargs), daemon=True))

        for listener in temporary_listeners:
            tasks.append(await curio.spawn(self._temporary_wrapper(event_name, listener, ctx, *args, **kwargs),
                                           daemon=True))

        return tasks

    # Gateway functions
    async def change_status(self, game: Game = None, status: Status = Status.ONLINE,
                            shard_id: int = 0):
        """
        Changes the bot's current status.

        :param game: The game object to use. None for no game.
        :param status: The new status. Must be a :class:`Status` object.
        :param shard_id: The shard to change your status on.
        """
        gateway = self._gateways[shard_id]
        return await gateway.send_status(game, status)

    async def wait_for(self, event_name: str, predicate: typing.Callable = None):
        """
        Wait for an event to happen in the gateway.

        You can specify a check to happen to check if this event is the one to return.
        When the check returns True, the listener is removed and the event data is returned.
        For example, to wait for a message with the content `Heck`:

        .. code:: python

            message = await client.wait_for("message_create", predicate=lambda m: m.content == "Heck")

        You can pass any function to this predicate. If this function takes an error, it will remove the listener,
        then raise into your code.

        .. code:: python

            async def _closure(message):
                if message.author.id != 66237334693085184:
                    return False

                if message.content == "sparkling water > tap water":
                    return True

                return False

            wrong = await client.wait_for("message_create", predicate=_closure)

        :param event_name: The name of the event to wait for.
        :param predicate: An optional check function to return.
        :return: The result of the event.
        """
        if predicate is None:
            predicate = lambda *args, **kwargs: True

        event = curio.Event()
        result = None
        _exc = None

        async def __event_listener_inner(ctx: EventContext, *args, **kwargs):
            try:
                is_result = predicate(*args, **kwargs)
                if inspect.isawaitable(is_result):
                    is_result = await is_result
            except Exception as e:
                # It is NOT the result we want.
                nonlocal _exc
                _exc = e
                await event.set()
                # Return True so this listener dies.
                return True
            else:
                if is_result:
                    # It is the result we want, so set the event.
                    await event.set()
                    # Then we store the result.
                    nonlocal result
                    result = args  # TODO: Figure out keyword arguments
                    return True

                return False

        self.add_listener(event_name, __event_listener_inner)
        # Wait on the event to be set.
        try:
            await event.wait()
        except curio.CancelledError:
            # remove the listener
            self.remove_listener_early(event_name, __event_listener_inner)
            raise
        # If it's an exception, raise the exception.
        if _exc is not None:
            raise _exc
        # Otherwise, return the event result.
        return result

    # HTTP Functions
    async def edit_profile(self, *,
                           username: str = None,
                           avatar: bytes = None):
        """
        Edits the profile of this bot.

        The user is **not** edited in-place - instead, you must wait for the `USER_UPDATE` event to be fired on the
        websocket.

        :param username: The new username of the bot.
        :param avatar: The bytes-like object that represents the new avatar you wish to use.
        """
        if username:
            if not 2 <= len(username) <= 32:
                raise ValueError("Username must be 2-32 characters")

        if avatar:
            avatar = base64ify(avatar)

        await self.http.edit_profile(username, avatar)

    async def edit_avatar(self, path: str):
        """
        A higher-level way to change your avatar.
        This allows you to provide a path to the avatar file instead of having to read it in manually.

        :param path: The path-like object to the avatar file.
        """
        with open(path, 'rb') as f:
            await self.edit_profile(avatar=f.read())

    async def get_user(self, user_id: int) -> User:
        """
        Gets a user by ID.

        :param user_id: The ID of the user to get.
        :return: A new User object.
        """
        try:
            return self.state._users[user_id]
        except KeyError:
            return self.state.make_user(await self.http.get_user(user_id))

    async def get_webhook(self, webhook_id: int) -> Webhook:
        """
        Gets a webhook by ID.

        :param webhook_id: The ID of the webhook to get.
        :return: A new Webhook object.
        """
        return self.state.make_webhook(await self.http.get_webhook(webhook_id))

    async def get_invite(self, invite_code: str) -> Invite:
        """
        Gets an invite by code.

        :param invite_code: The invite code to get.
        :return: A new Invite object.
        """
        return Invite(self, **(await self.http.get_invite(invite_code)))

    # Utility functions
    async def connect(self, token: str = None, shard_id: int = 1):
        """
        Connects the bot to the gateway.

        This will NOT poll for events - only open a websocket connection!
        """
        from curious.gateway import Gateway

        if token:
            self._token = token

        if not self.http:
            self.http = HTTPClient(self._token)

        if not self.application_info:
            self.application_info = AppInfo(self, **(await self.http.get_application_info()))

        gateway_url = await self.get_gateway_url()
        self._gateways[shard_id] = await Gateway.from_token(self._token, self.state, gateway_url,
                                                            shard_id=shard_id, shard_count=self.shard_count)
        await self._gateways[shard_id].websocket.wait_for_ready()

        return self

    async def poll(self, shard_id: int):
        """
        Polls the gateway for the next event.

        :param shard_id: The shard ID of the gateway to shard.
        """
        from curious.gateway import ReconnectWebsocket
        gw = self._gateways[shard_id]
        while True:
            try:
                await gw.next_event()
            except WebsocketClosedError as e:
                # Try and handle the close.
                if e.reason == "Client closed connection":
                    # internal
                    return

                if e.code in [1000, 4007] or gw.session_id is None:
                    self._logger.info("Shard {} disconnected with code {}, creating new session".format(shard_id,
                                                                                                        e.code))
                    self.state._reset(gw.shard_id)
                    await gw.reconnect(resume=False)
                elif e.code not in (4004, 4011):
                    # Try and RESUME.
                    self._logger.info("Shard {} disconnected with close code {}, reason {}, "
                                      "attempting a reconnect.".format(shard_id, e.code, e.reason))
                    await gw.reconnect(resume=True)
                else:
                    raise
            except ReconnectWebsocket:
                # We've been told to reconnect, try and RESUME.
                await gw.reconnect(resume=True)

    async def start(self, token: str = None, shards: int = 1):
        """
        Starts the gateway polling loop.

        This is a convenience method that polls on all the shards at once. It will **not** restart them automatically.
        """
        self._logger.info("Starting bot with {} shards.".format(shards))
        self.shard_count = shards
        tasks = []
        for shard_id in range(0, shards):
            await self.connect(token, shard_id=shard_id)
            tasks.append(await curio.spawn(self.poll(shard_id)))
            self._logger.info("Sleeping for 5 seconds between shard creation.")
            await curio.sleep(5)

        wait = curio.wait(tasks)

        results = []

        # Wait for the next task.
        while True:
            task = await wait.next_done()  # type: curio.Task
            if task is None:
                break

            try:
                result = await task.join()
            except Exception as e:
                result = e
            finally:
                results.append(result)

        return results

    async def start_autosharded(self, token: str = None):
        """
        Starts the bot with an automatically set number of shards.
        """
        if token:
            self._token = token

        if not self.http:
            self.http = HTTPClient(self._token)

        shards = await self.get_shard_count()
        self.shard_count = shards
        await self.start(token, shards=shards)

    def run(self, token: str = None, shards: typing.Union[int, object] = 1):
        """
        Runs your bot with Curio with the monitor enabled.

        :param token: The token to run with.
        :param shards: The number of shards to run.
            If this is None, the bot will autoshard.
        """
        try:
            kernel = curio.Kernel(with_monitor=True, warn_if_task_blocks_for=5)
        except TypeError:
            # old vers of curio
            kernel = curio.Kernel(with_monitor=True)
        if shards == AUTOSHARD:
            coro = self.start_autosharded(token)
        else:
            coro = self.start(token, shards=shards)

        try:
            return kernel.run(coro=coro, shutdown=True)
        except (KeyboardInterrupt, EOFError):
            self._logger.info("C-c/C-d received, killing bot.")
            # Cleanup.
            coros = []
            for gateway in self._gateways.values():
                coros.append(gateway.websocket.close_now(1000, reason="Client closed connection"))
                coros.append(gateway._close())

            async def __cleanup():
                tasks = []
                for task in coros:
                    tasks.append(await curio.spawn(task))

                self._logger.info("Need to wait for {} task(s) to complete.".format(len(tasks)))

                # silence exceptions
                await curio.gather(tasks, return_exceptions=True)
                self._logger.info("Clean-up complete.")
                raise SystemExit()

            return kernel.run(coro=__cleanup())

    @classmethod
    def from_token(cls, token: str = None):
        """
        Starts a bot from a token object.

        :param token: The token to use for the bot.
        """
        bot = cls(token)
        return bot.run()
