import base64
import functools
import inspect
import typing
import imghdr

import curio
import logging
import multidict
from cuiows.exc import WebsocketClosedError
from curio.task import Task

from curious.dataclasses.status import Game, Status
from curious.dataclasses.user import User
from curious.gateway import Gateway, ReconnectWebsocket
from curious.http import HTTPClient
from curious.state import State


class AppInfo(object):
    def __init__(self, client: 'Client', **kwargs):
        #: The client ID of this application.
        self.client_id = int(kwargs.pop("id", 0))

        #: The owner of this application.
        self.owner = User(client, **kwargs.pop("owner"))

        #: The description of this application.
        self.description = kwargs.pop("description")


class Client(object):
    """
    The main client class.

    This is used to interact with Discord.
    """

    def __init__(self, token: str = None):
        """
        :param token: The current token for this bot.
            This can be passed as None and can be initialized later.
        """
        #: The gateway connection.
        #: This is automatically created when `start()` is called on the bot.
        self.gw = None  # type: Gateway

        #: The token for the bot.
        self._token = token

        #: The current connection state for the bot.
        self.state = State(self)

        #: The current event storage.
        self.events = multidict.MultiDict()

        #: The HTTPClient used for this bot.
        self.http = None  # type: HTTPClient

        #: The cached gateway URL.
        self._gw_url = None  # type: str

        #: The application info for this bot.
        self.application_info = None  # type: AppInfo

        #: The logger for this bot.
        self.logger = logging.getLogger("curious.client")

        # Scan the dict of this object, to check for all events registered under it.
        # This is useful, for example, for subclasses.
        for name, obb in self.__dict__.items():
            if name.startswith("on_") and inspect.iscoroutinefunction(obb):
                self.add_event(name[3:], obb, bound=True)

    @property
    def user(self) -> User:
        return self.state._user

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

    # Events
    def add_event(self, name: str, func, *,
                  bound: bool = False):
        """
        Add an event to the internal registry of events.

        :param name: The event name to register under.
        :param func: The function to add.
        :param bound: If this is True, then the Client won't be passed as the first argument.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Event must be a coroutine function")

        if bound:
            original_func = func

            @functools.wraps(func)
            async def _bound_wrapper(client: Client, *args, **kwargs):
                await original_func(*args, **kwargs)

            func = _bound_wrapper

        self.events.add(name, func)

    def event(self, func):
        """
        Marks a function as an event.

        This will copy it to the events dictionary, where it will be used as an event later on.

        :param func: The function to mark as an event.
        :return: The unmodified function.
        """
        if not func.__name__.startswith("on_"):
            raise ValueError("Events must start with on_")

        event = func.__name__[3:]
        self.add_event(event, func)

    async def _error_wrapper(self, func, *args, **kwargs):
        try:
            await func(*args, **kwargs)
        except Exception as e:
            self.logger.exception("Unhandled exception in {}!".format(func.__name__))

    async def fire_event(self, event_name: str, *args, **kwargs) -> typing.List[Task]:
        """
        Fires an event to run.

        This will wrap the events in Tasks and return a list of them.

        :param event_name: The event name to fire.
        :return: A :class:`list` of :class:`curio.task.Task` representing the events.
        """
        coros = self.events.getall(event_name, [])
        if not coros:
            return []

        self.logger.debug("Dispatching event {} to {} listeners".format(event_name, len(coros)))

        tasks = []
        for event in coros:
            tasks.append(await curio.spawn(self._error_wrapper(event, self, *args, **kwargs)))

        return tasks

    # Gateway functions
    async def change_status(self, game: Game = None, status: Status = Status.ONLINE):
        """
        Changes the bot's current status.

        :param game: The game object to use. None for no game.
        :param status: The new status. Must be a :class:`Status` object.
        """
        return self.gw.send_status(game, status)

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
        if avatar:
            # Convert the avatar to base64.
            mimetype = imghdr.what(None, avatar)
            if not mimetype:
                raise ValueError("Invalid image type")

            b64_data = base64.b64encode(avatar).decode()
            avatar = "data:{};base64,{}".format(mimetype, b64_data)

        await self.http.edit_profile(username, avatar)

    async def edit_avatar(self, path: str):
        """
        A higher-level way to change your avatar.

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
        return User(self, **(await self.http.get_user(user_id)))

    # Utility functions
    async def connect(self, token: str = None):
        """
        Connects the bot to the gateway.

        This will NOT poll for events - only open a websocket connection!
        """
        if token:
            self._token = token

        self.http = HTTPClient(self._token)

        self.application_info = AppInfo(self, **(await self.http.get_application_info()))

        gateway_url = await self.get_gateway_url()
        self.gw = await Gateway.from_token(self._token, self.state, gateway_url)
        await self.gw.websocket.wait_for_ready()

        return self

    async def start(self, token: str = None):
        """
        Starts the gateway polling loop.
        """
        await self.connect(token)

        while True:
            try:
                await self.gw.next_event()
            except WebsocketClosedError as e:
                # Try and handle the close.
                if e.code not in (1000, 4004):
                    # Try and RESUME.
                    self.logger.info("Disconnected with close code {}, attempting a reconnect.".format(e.code))
                    await self.gw.reconnect(resume=True)
                else:
                    raise
            except ReconnectWebsocket:
                # We've been told to reconnect, try and RESUME.
                await self.gw.reconnect(resume=True)
