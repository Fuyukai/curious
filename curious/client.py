import importlib
import inspect

import re
import traceback

import sys
import typing
import logging

import curio
import multidict
from cuiows.exc import WebsocketClosedError
from curio.task import Task

from curious.commands import context
from curious.commands import plugin
from curious.commands import cmd
from curious.dataclasses.guild import Guild
from curious.dataclasses.invite import Invite
from curious.dataclasses.message import Message
from curious.dataclasses.status import Game, Status
from curious.dataclasses.user import User
from curious.dataclasses.webhook import Webhook
from curious.event import EventContext, event as ev_dec
from curious.http.httpclient import HTTPClient
from curious.util import base64ify, attrdict

AUTOSHARD = object()


def split_message_content(content: str, delim: str = " ") -> typing.List[str]:
    """
    Splits a message into individual parts by `delim`, returning a list of strings.
    This method preserves quotes.

    :param content: The message content to split.
    :param delim: The delimiter to split on.
    :return: A list of items split
    """

    def replacer(m):
        return m.group(0).replace(delim, "\x00")

    parts = re.sub(r'".+?"', replacer, content).split()
    parts = [p.replace("\x00", " ") for p in parts]
    return parts


def _default_msg_func_factory(prefix: str):
    def __inner(bot: Client, message):
        matched = None
        if isinstance(prefix, str):
            match = message.content.startswith(prefix)
            if match:
                matched = prefix

        elif isinstance(prefix, list):
            for i in prefix:
                if message.content.startswith(i):
                    matched = i
                    break

        if not matched:
            return None

        tokens = split_message_content(message.content[len(matched):])
        command_word = tokens[0]

        return command_word, tokens[1:], matched

    __inner.prefix = prefix
    return __inner


class AppInfo(object):
    """
    Represents the application info for an OAuth2 application.
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
                 enable_commands: bool = True,
                 command_prefix: typing.Union[str, list] = None,
                 message_check=None,
                 description: str = "The default curious description",
                 state_klass: type = None):
        """
        :param token: The current token for this bot.
            This can be passed as None and can be initialized later.
            
        :param enable_commands: Should commands integration be enabled?
            If this is False, commands can still be registered etc, they just won't fire (the event won't appear).
        
        :param command_prefix: The command prefix for this bot.
        :param message_check: The message check function for this bot. 
            This should take two arguments, the client and message, and should return either None or a 3-item tuple:
              - The command word matched
              - The tokens after the command word
              - The prefix that was matched.
              
        :param description: The description of this bot for usage in the default help command.
            
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

        if enable_commands:
            if not command_prefix and not message_check:
                raise TypeError("Must provide one of `command_prefix` or `message_check`")

            self._message_check = message_check or _default_msg_func_factory(command_prefix)
        else:
            self._message_check = lambda x: None

        #: The description of this bot.
        self.description = description

        #: The dictionary of command objects to use.
        self.commands = attrdict()

        #: The dictionary of plugins to use.
        self.plugins = {}

        self._plugin_modules = {}

        if enable_commands:
            # Add the handle_commands as a message_create event.
            self.add_event(self.handle_commands)

            from curious.commands.plugin_core import _Core
            self.add_plugin(_Core(self))

        self.scan_events()

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
    def add_event(self, func, name: str = None):
        """
        Add an event to the internal registry of events.

        :param name: The event name to register under.
        :param func: The function to add.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Event must be a coroutine function")

        if name is None:
            name = func.event

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

    def event(self, name: str):
        """
        A convenience decorator to mark a function as an event.

        This will copy it to the events dictionary, where it will be used as an event later on.

        :param name: The name of the event.
        """

        def _inner(func):
            f = ev_dec(name)(func)
            self.add_event(func=f)

        return _inner

    def scan_events(self):
        """
        Scans this class for functions marked with an event decorator.
        """
        for _, item in inspect.getmembers(self, predicate=lambda x: hasattr(x, "event") and getattr(x, "scan", False)):
            self._logger.info("Registering event function {} for event {}".format(_, item.event))
            self.add_event(item)

    async def _error_wrapper(self, func, *args, **kwargs):
        try:
            await func(*args, **kwargs)
        except Exception as e:
            self._logger.exception("Unhandled exception in {}!".format(func.__name__))

    async def _wrap_context(self, ctx: 'context.Context'):
        """
        Wraps a context in a safety wrapper.

        This will dispatch `command_exception` when an error happens.
        """
        try:
            await ctx.invoke()
        except Exception as e:
            gw = self._gateways[ctx.event_context.shard_id]
            await self.fire_event("command_error", e, ctx=ctx, gateway=gw)

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

    # commands
    @ev_dec("command_error", scan=False)
    async def default_command_error(self, ctx, e):
        """
        Default error handler.

        This is meant to be overriden - normally it will just print the traceback.
        """
        if len(self.events.getall("command_error")) >= 2:
            # remove ourselves
            self.remove_event("command_error", self.default_command_error)
            return

        traceback.print_exception(None, e, e.__traceback__)

    @ev_dec("message_create", scan=False)
    async def handle_commands(self, event_ctx: EventContext, message: Message):
        """
        Handles invokation of commands.

        This is added as an event during initialization.
        """
        if not message.content:
            # Minor optimization - don't fire on empty messages.
            return

        # use the message check function
        _ = self._message_check(self, message)
        if inspect.isawaitable(_):
            _ = await _

        if not _:
            # not a command, do not bother
            return

        # func should return command_word and args for the command
        command_word, args, prefix = _
        command = self.get_command(command_word)
        if command is None:
            return

        # Create the context object that will be passed in.
        ctx = context.Context(self, command=command, message=message,
                              event_ctx=event_ctx)
        ctx.prefix = prefix
        ctx.name = command_word
        ctx.raw_args = args

        await curio.spawn(self._wrap_context(ctx))

    def add_command(self, command_name: str, command: 'command.Command'):
        """
        Adds a command to the internal registry of commands.

        :param command_name: The name of the command to add.
        :param command: The command object to add.
        """
        if command_name in self.commands:
            if not self.commands[command_name]._overridable:
                raise ValueError("Command {} already exists".format(command_name))
            else:
                self.commands.pop(command_name)

        self.commands[command_name] = command

    def add_plugin(self, plugin_class):
        """
        Adds a plugin to the bot.

        :param plugin_class: The plugin class to add.
        """
        events, commands = plugin_class._scan_body()

        for event in events:
            event.plugin = plugin_class
            self.events.add(event.event, event)

        for command in commands:
            # Bind the command to the plugin.
            command.instance = plugin_class
            # dont add any aliases
            self.add_command(command.name, command)

        self.plugins[plugin_class.name] = plugin_class

    async def load_plugins_from(self, import_name: str, *args, **kwargs):
        """
        Loads a plugin and adds it to the internal registry.

        :param import_name: The import name of the plugin to add (e.g `bot.plugins.moderation`).
        """
        module = importlib.import_module(import_name)
        mod = [module, []]

        # Locate all of the Plugin types.
        for name, member in inspect.getmembers(module):
            if not isinstance(member, type):
                # We only want to inspect instances of type (i.e classes).
                continue

            inherits = inspect.getmro(member)
            # remove `member` from the mro
            # this prevents us registering Plugin as a plugin
            inherits = [i for i in inherits if i != member]
            if plugin.Plugin not in inherits:
                # Only inspect instances of plugin.
                continue

            if not hasattr(member, "__dict__"):
                # don't be difficult
                continue

            # evil cpython type implementation detail abuse
            if member.__dict__.get("_include_in_scan", True) is False:
                # this won't show up for subclasses.
                # so they always have to be explicitly set
                continue

            # Assume it has a setup method on it.
            result = member.setup(self, *args, **kwargs)
            if inspect.isawaitable(result):
                result = await result

            # Add it to the list of plugins we need to destroy when unloading.
            # We add the type, not the instance, as the instances are destroyed separately.
            mod[1].append(member)

        if len(mod[1]) == 0:
            raise ValueError("Plugin contained no plugin classes (classes that inherit from Plugin)")

        self._plugin_modules[import_name] = mod

    async def unload_plugins_from(self, import_name: str):
        """
        Unloads plugins from the specified import name.

        This is the opposite to :meth:`load_plugins_from`.
        """
        mod, plugins = self._plugin_modules[import_name]
        # we can't do anything with the module currently because it's still in our locals scope
        # so we have to wait to delete it
        # i'm not sure this is how python imports work but better to be safe
        # (especially w/ custom importers)

        for plugin in plugins:
            # find all the Command instances with this plugin as the body
            for name, command in self.commands.copy().items():
                # isinstance() checks ensures that the type of the instance is this plugin
                if isinstance(command.instance, plugin):
                    # make sure the instance isn't lingering around
                    command.instance = None
                    # rip
                    self.commands.pop(name)

            # remove all events registered
            for name, event in self.events.copy().items():
                # not a plugin event
                if not hasattr(event, "plugin"):
                    continue
                if isinstance(event.plugin, plugin):
                    event.plugins = None
                    self.remove_event(name, event)

            # now that all commands are dead, call `unload()` on all of the instances
            for name, instance in self.plugins.copy().items():
                if isinstance(instance, plugin):
                    r = instance.unload()
                    if inspect.isawaitable(r):
                        await r

                    self.plugins.pop(name)

        # remove from sys.modules and our own registry to remove all references
        del sys.modules[import_name]
        del self._plugin_modules[import_name]
        del mod

    def get_commands_for(self, plugin: 'plugin.Plugin') -> typing.Generator['cmd.Command', None, None]:
        """
        Gets the commands for the specified plugin.

        :param plugin: The plugin instance to get commands of.
        :return: A list of :class:`Command`.
        """
        for command in self.commands.copy().values():
            if command.instance == plugin:
                yield command

    def get_command(self, command_name: str) -> typing.Union['cmd.Command', None]:
        """
        Gets a command object for the specified command name.

        :param command_name: The name of the command.
        :return: The command object if found, otherwise None.
        """

        def _f(cmd: cmd.Command):
            return cmd.can_be_invoked_by(command_name)

        f = filter(_f, self.commands.values())
        return next(f, None)

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
