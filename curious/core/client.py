"""
The main client class.

This contains a definition for :class:`.Client` which is used to interface primarily with Discord.

.. currentmodule:: curious.core.client
"""

import collections
import enum
import inspect
import logging
import traceback
import typing
from types import MappingProxyType

import curio
from asyncwebsockets import WebsocketClosed
from curio.monitor import MONITOR_HOST, MONITOR_PORT, Monitor
from curio.task import TaskGroup

from curious.core.event import EventManager, event as ev_dec
from curious.core.httpclient import HTTPClient
from curious.dataclasses import channel as dt_channel, guild as dt_guild, member as dt_member
from curious.dataclasses.appinfo import AppInfo
from curious.dataclasses.invite import Invite
from curious.dataclasses.presence import Game, Status
from curious.dataclasses.user import BotUser, User
from curious.dataclasses.webhook import Webhook
from curious.dataclasses.widget import Widget
from curious.exc import CuriousError
from curious.util import base64ify

#: A sentinel value to indicate that the client should automatically shard.
AUTOSHARD = object()

logger = logging.getLogger("curious.client")


class BotType(enum.IntEnum):
    """
    An enum that signifies what type of bot this bot is.
    
    This will tell the commands handling how to respond, as well as how to log in.
    """
    #: Regular bot. This signifies that the client should log in as a bot account.
    BOT = 1

    #: User bot. This signifies that the client should log in as a user account.
    USERBOT = 2

    # 4 is reserved

    #: No bot responses. This signifies that the client should respond to ONLY USER messages.
    ONLY_USER = 8

    #: No DMs. This signifies the bot only works in guilds.
    NO_DMS = 16

    #: No guilds. This signifies the bot only works in DMs.
    NO_GUILDS = 32

    #: Self bot. This signifies the bot only responds to itself.
    SELF_BOT = 64


class Client(object):
    """
    The main client class. This is used to interact with Discord.

    When creating a client object, you can either pass a token explicitly, or pass in in the 
    :meth:`start` call or similar.

    .. code:: python

        bot = Client("'a'")  # pass explicitly
        bot.run("'b'")  # or pass to the run call.

    """
    #: A list of events to ignore the READY status.
    IGNORE_READY = [
        "connect",
        "guild_streamed",
        "guild_chunk",
        "guild_available",
        "guild_sync"
    ]

    def __init__(self, token: str = None, *,
                 state_klass: type = None,
                 bot_type: int = (BotType.BOT | BotType.ONLY_USER)):
        """
        :param token: The current token for this bot.  
            This can be passed as None and can be initialized later.
            
        :param state_klass: The class to construct the connection state from.
        
        :param bot_type: A union of :class:`~.BotType` that defines the type of this bot.
        """
        #: The mapping of `shard_id -> gateway` objects.
        self._gateways = {}

        #: The number of shards this client has.
        self.shard_count = 0

        #: The token for the bot.
        self._token = token

        if state_klass is None:
            from curious.core.state import State
            state_klass = State

        #: The current connection state for the bot.
        self.state = state_klass(self)

        #: The bot type for this bot.
        self.bot_type = bot_type

        if self.bot_type & BotType.BOT and self.bot_type & BotType.USERBOT:
            raise ValueError("Bot cannot be a bot and a userbot at the same time")

        #: The current :class:`.EventManager` for this bot.
        self.events = EventManager()

        #: The :class:`~.HTTPClient` used for this bot.
        self.http = None  # type: HTTPClient

        #: The cached gateway URL.
        self._gw_url = None  # type: str

        #: The application info for this bot.
        #: Instance of :class:`~.AppInfo`.
        #: This will be None for user bots.
        self.application_info = None  # type: AppInfo

        self.scan_events()

    def create_http(self):
        """
        Creates the :class:`~.HTTPClient` for this bot.
        
        This requires that the token is set on ``self.token``.
        """
        if not self.http:
            self.http = HTTPClient(self._token, bot=bool(self.bot_type & BotType.BOT))

    @property
    def user(self) -> BotUser:
        """
        :return: The :class:`~.User` that this client is logged in as.
        """
        return self.state._user

    @property
    def guilds(self) -> 'typing.Mapping[int, dt_guild.Guild]':
        """
        :return: A mapping of int -> :class:`~.Guild` that this client can see.
        """
        return self.state.guilds

    @property
    def invite_url(self):
        """
        :return: The invite URL for this bot.
        """
        return "https://discordapp.com/oauth2/authorize?client_id={}&scope=bot".format(
            self.application_info.client_id)

    @property
    def events_handled(self) -> collections.Counter:
        """
        A :class:`collections.Counter` of all events that have been handled since the bot's bootup.
        This can be used to track statistics for events.
         
        .. code-block:: python3
        
            @command()
            async def events(self, ctx: Context):
                '''
                Shows the most common events.
                '''
                
                ev = ctx.bot.events_handled.most_common(3)
                await ctx.channel.send(", ".join("{}: {}".format(*x) for x in ev)
        
        """

        c = collections.Counter()
        for gw in self._gateways.values():
            c.update(gw._dispatches_handled)

        return c

    @property
    def gateways(self):
        """
        :return: A read-only view of the current gateways for this client. 
        """
        return MappingProxyType(self._gateways)

    def find_channel(self, channel_id: int):
        """
        Finds a channel by channel ID.
        """
        return self.state.find_channel(channel_id)

    async def get_gateway_url(self) -> str:
        """
        :return: The gateway URL for this bot.
        """
        if self._gw_url:
            return self._gw_url

        self._gw_url = await self.http.get_gateway_url()
        return self._gw_url

    async def get_shard_count(self) -> int:
        """
        :return: The shard count recommended for this bot.
        """
        gw, shards = await self.http.get_shard_count()
        self._gw_url = gw

        return shards

    def guilds_for(self, shard_id: int) -> 'typing.Iterable[dt_guild.Guild]':
        """
        Gets the guilds for this shard.

        :param shard_id: The shard ID to get guilds from.
        :return: A list of :class:`Guild` that client can see on the specified shard.
        """
        return self.state.guilds_for_shard(shard_id)

    def event(self, name: str):
        """
        A convenience decorator to mark a function as an event.

        This will copy it to the events dictionary, where it will be used as an event later on.

        .. code-block:: python3
        
            @bot.event("message_create")
            async def something(ctx, message: Message):
                pass

        :param name: The name of the event.
        """

        def _inner(func):
            f = ev_dec(name)(func)
            self.events.add_event(func=f)

        return _inner

    def scan_events(self):
        """
        Scans this class for functions marked with an event decorator.
        """

        def _pred(f):
            if not hasattr(f, "events"):
                return False

            if getattr(f, "scan", False):
                return True

            return False

        for _, item in inspect.getmembers(self, predicate=_pred):
            logger.info("Registering event function {} for events {}".format(_, item.events))
            self.events.add_event(item)

    # rip in peace old fire_event
    # 2016-2017
    # broke my pycharm
    async def fire_event(self, event_name: str, *args, **kwargs):
        """
        Fires an event.

        This actually passes the arguments to :meth:`.EventManager.fire_event`.
        """
        gateway = kwargs.get("gateway")
        if not self.state.is_ready(gateway.shard_id):
            if event_name not in self.IGNORE_READY and not event_name.startswith("gateway_"):
                return

        return await self.events.fire_event(event_name, *args, **kwargs, client=self)

    async def wait_for(self, *args, **kwargs):
        """
        Shortcut for :meth:`.EventManager.wait_for`.
        """
        return await self.events.wait_for(*args, **kwargs)

    # Gateway functions
    async def change_status(self, game: Game = None, status: Status = Status.ONLINE,
                            afk: bool = False,
                            shard_id: int = 0, *, sync: bool = False):
        """
        Changes the bot's current status.

        :param game: The game object to use. None for no game.
        :param status: The new status. Must be a :class:`~.Status` object.
        :param afk: Is the bot AFK? Only useful for userbots.
        :param shard_id: The shard to change your status on.
        :param sync: Sync status with other clients? Only useful for userbots.
        """
        if not self.user.bot and sync:
            # update `status` key of settings
            await self.user.settings.update(status=status.value)

        gateway = self._gateways[shard_id]
        return await gateway.send_status(game, status, afk=afk)

    # HTTP Functions
    async def edit_profile(self, *,
                           username: str = None,
                           avatar: bytes = None,
                           password: str = None):
        """
        Edits the profile of this bot.

        The user is **not** edited in-place - instead, you must wait for the `USER_UPDATE` event to
        be fired on the websocket.

        :param username: The new username of the bot.
        :param avatar: The bytes-like object that represents the new avatar you wish to use.
        :param password: The password to use. Only for user accounts.
        """
        if not self.user.bot and password is None:
            raise ValueError("Password must be passed for user bots")

        if username:
            if any(x in username for x in ('@', ':', '```')):
                raise ValueError("Username must not contain banned characters")

            if any(x == username for x in ("discordtag", "everyone", "here")):
                raise ValueError("Username cannot be a banned username")

            if not 2 <= len(username) <= 32:
                raise ValueError("Username must be 2-32 characters")

        if avatar:
            avatar = base64ify(avatar)

        await self.http.edit_user(username, avatar, password)

    async def edit_avatar(self, path: str):
        """
        A higher-level way to change your avatar.
        This allows you to provide a path to the avatar file instead of having to read it in 
        manually.

        :param path: The path-like object to the avatar file.
        """
        with open(path, 'rb') as f:
            return await self.edit_profile(avatar=f.read())

    async def get_user(self, user_id: int) -> User:
        """
        Gets a user by ID.

        :param user_id: The ID of the user to get.
        :return: A new :class:`~.User` object.
        """
        try:
            return self.state._users[user_id]
        except KeyError:
            u = self.state.make_user(await self.http.get_user(user_id))
            # decache it if we need to
            self.state._check_decache_user(u.id)
            return u

    async def get_application(self, application_id: int) -> AppInfo:
        """
        Gets an application by ID.

        :param application_id: The client ID of the application to fetch.
        :return: A new :class:`~.AppInfo` object corresponding to the application.
        """
        data = await self.http.get_app_info(application_id=application_id)
        appinfo = AppInfo(self, **data)

        return appinfo

    async def get_webhook(self, webhook_id: int) -> Webhook:
        """
        Gets a webhook by ID.

        :param webhook_id: The ID of the webhook to get.
        :return: A new :class:`~.Webhook` object.
        """
        return self.state.make_webhook(await self.http.get_webhook(webhook_id))

    async def get_invite(self, invite_code: str, *,
                         with_counts: bool = True) -> Invite:
        """
        Gets an invite by code.

        :param invite_code: The invite code to get.
        :param with_counts: Return the approximate counts for this invite?
        :return: A new :class:`~.Invite` object.
        """
        return Invite(self, **(await self.http.get_invite(invite_code, with_counts=with_counts)))

    async def get_widget(self, guild_id: int) -> Widget:
        """
        Gets a widget from a guild.
        
        :param guild_id: The ID of the guild to get the widget of. 
        :return: A :class:`~.Widget` object.
        """
        data = await self.http.get_widget_data(guild_id)
        return Widget(self, **data)

    # download_ methods
    async def download_guild_member(self, guild_id: int, member_id: int) -> 'dt_member.Member':
        """
        Downloads a :class:`~.Member` over HTTP.
        
        .. warning::
            
            The :attr:`~.Member.roles` and similar fields will be empty when downloading a Member, 
            unless the guild was in cache.
        
        :param guild_id: The ID of the guild which the member is in. 
        :param member_id: The ID of the member to get.
        :return: The :class:`~.Member` object downloaded.
        """
        member_data = await self.http.get_guild_member(guild_id=guild_id, member_id=member_id)
        member = dt_member.Member(self, **member_data)
        # this is enough to pick up the cache
        member.guild_id = guild_id

        # manual refcounts :ancap:
        self.state._check_decache_user(member.id)

        return member

    async def download_guild_members(self, guild_id: int, *,
                                     after: int = None, limit: int = 1000,
                                     get_all: bool = True) -> 'typing.Iterable[dt_member.Member]':
        """
        Downloads the members for a :class:`~.Guild` over HTTP.
        
        .. warning::
        
            This can take a long time on big guilds.
        
        :param guild_id: The ID of the guild to download members for.
        :param after: The member ID after which to get members for.
        :param limit: The maximum number of members to return. By default, this is 1000 members.
        :param get_all: Should *all* members be fetched?
        :return: An iterable of :class:`~.Member`.
        """
        member_data = []
        if get_all is True:
            last_id = 0
            while True:
                next_data = await self.http.get_guild_members(guild_id=guild_id, limit=limit,
                                                              after=last_id)
                # no more members to get
                if not next_data:
                    break

                member_data.extend(next_data)
                # if there's less data than limit, we are finished downloading members
                if len(next_data) < limit:
                    break

                last_id = member_data[-1]["user"]["id"]
        else:
            next_data = await self.http.get_guild_members(guild_id=guild_id, limit=limit,
                                                          after=after)
            member_data.extend(next_data)

        # create the member objects
        members = []
        for datum in member_data:
            m = dt_member.Member(self, **datum)
            m.guild_id = guild_id
            members.append(m)

        return members

    async def download_channels(self, guild_id: int) -> 'typing.List[dt_channel.Channel]':
        """
        Downloads all the :class:`~.Channel` for a Guild.
        
        :param guild_id: The ID of the guild to download channels for. 
        :return: An iterable of :class:`~.Channel` objects.
        """
        channel_data = await self.http.get_guild_channels(guild_id=guild_id)
        channels = []
        for datum in channel_data:
            channel = dt_channel.Channel(self, **datum)
            channel.guild_id = guild_id
            channels.append(channel)

        return channels

    async def download_guild(self, guild_id: int, *,
                             full: bool = False) -> 'dt_guild.Guild':
        """
        Downloads a :class:`~.Guild` over HTTP.
        
        .. warning::
        
            If ``full`` is True, this will fetch and fill ALL objects of the guild, including 
            channels and members. This can take a *long* time if the guild is large.
        
        :param guild_id: The ID of the Guild object to download. 
        :param full: If all extra data should be downloaded alongside it.
        :return: The :class:`~.Guild` object downloaded.
        """
        guild_data = await self.http.get_guild(guild_id)
        # create the new guild using the data specified
        guild = dt_guild.Guild(self, **guild_data)
        guild.unavailable = False

        # update the guild store
        self.state._guilds[guild_id] = guild

        if full:
            # download all of the members
            members = await self.download_guild_members(guild_id=guild_id, get_all=True)
            # update the `_members` dict
            guild._members = {m.id: m for m in members}

            # download all of the channels
            channels = await self.download_channels(guild_id=guild_id)
            guild._channels = {c.id: c for c in channels}

        return guild

    # Utility functions
    async def connect(self, token: str = None, shard_id: int = 1,
                      *, large_threshold: int = 250, **kwargs):
        """
        Connects the bot to the gateway.

        This will NOT poll for events - only open a websocket connection!
        """
        from curious.core.gateway import Gateway

        if token:
            self._token = token

        self.create_http()

        if not self.application_info and self.bot_type & BotType.BOT:
            self.application_info = AppInfo(self, **(await self.http.get_app_info(None)))

        gateway_url = await self.get_gateway_url()
        self._gateways[shard_id] = await Gateway.from_token(self._token, self.state, gateway_url,
                                                            shard_id=shard_id,
                                                            shard_count=self.shard_count,
                                                            large_threshold=large_threshold)

        return self

    async def poll(self, shard_id: int):
        """
        Polls the gateway for the next event.

        :param shard_id: The shard ID of the gateway to shard.
        """
        from curious.core.gateway import ReconnectWebsocket
        gw = self._gateways[shard_id]
        while True:
            try:
                await gw.next_event()
            except WebsocketClosed as e:
                # Try and handle the close.
                if e.reason == "Client closed connection":
                    # internal
                    return

                if e.code in [1000, 4007] or gw.session_id is None:
                    logger.info("Shard {} disconnected with code {}, "
                                "creating new session".format(shard_id, e.code))
                    self.state._reset(gw.shard_id)
                    await gw.reconnect(resume=False)
                elif e.code not in (4004, 4011):
                    # Try and RESUME.
                    logger.info("Shard {} disconnected with close code {}, reason {}, "
                                "attempting a reconnect.".format(shard_id, e.code, e.reason))
                    await gw.reconnect(resume=True)
                else:
                    raise
            except ReconnectWebsocket:
                # We've been told to reconnect, try and RESUME.
                await gw.reconnect(resume=True)

    async def boot_shard(self, shard_id: int, shard_count: int = None,
                         **kwargs) -> curio.Task:
        """
        Boots a single gateway shard.
        
        This can be used to run multiple clients instead of having a single client shard.
        
        :param shard_id: The shard ID to boot. 
        :param shard_count: The number of shards being created.
        :return: The :class:`curio.Task` that represents the polling loop.
        """
        if shard_count:
            self.shard_count = shard_count

        logger.info(f"Spawning shard {shard_id}")
        await self.connect(token=self._token, shard_id=shard_id, **kwargs)
        if "task_group" in kwargs:
            spawn = kwargs["task_group"].spawn
        else:
            spawn = curio.spawn

        t = await spawn(self.poll(shard_id))
        t.task_local_storage["shard_id"] = {"id": shard_id}
        return t

    async def start(self, shards: int = 1, **kwargs):
        """
        Starts the gateway polling loop.

        This is a convenience method that polls on all the shards at once.
        This will **only reboot safely returned shards.** Erroring shards won't be rebooted.
        """
        logger.info("Starting bot with {} shards.".format(shards))
        self.shard_count = shards
        results = []

        async with TaskGroup(name="shard waiter") as g:
            for shard_id in range(0, shards):
                shard_listener = await self.boot_shard(shard_id, task_group=g, **kwargs)
                logger.info("Sleeping for 5 seconds between shard creation.")
                if shard_id < shards - 1:
                    await curio.sleep(5)

            while True:
                task = await g.next_done()  # type: curio.Task
                if task is None:
                    break

                try:
                    result = await task.join()
                except Exception as e:
                    result = e
                    # format custom exception
                    exc = traceback.format_exception(None, e.__cause__, e.__cause__.__traceback__)
                    exc = ''.join(exc)

                    logger.error("Shard {} crashed, not rebooting it.\n{}"
                                 .format(task.task_local_storage["shard_id"]["id"], exc))
                else:
                    # reboot it
                    logger.warning("Rebooting shard {}.".format(task.id))
                    shard_id = task.task_local_storage["shard_id"]["id"]
                    t = await self.boot_shard(shard_id=shard_id)
                    t.task_local_storage["shard_id"] = {"id": shard_id}
                    # add the shard waiter task
                    g.add_task(t)
                finally:
                    results.append(result)

        # if we're still here, cancel a bunch of stuff
        for gateway in self._gateways.values():
            await gateway.close()

        return results

    async def start_autosharded(self, token: str = None, **kwargs):
        """
        Starts the bot with an automatically set number of shards.
        """
        if token:
            self._token = token

        self.create_http()

        shards = await self.get_shard_count()
        self.shard_count = shards
        await self.start(shards=shards, **kwargs)

    async def _cleanup(self):
        """
        Performs cleanup.
        """
        for gateway in self._gateways.values():
            await gateway.close()

    def run(self, token: str = None, shards: typing.Union[int, object] = 1, *,
            monitor_host: str = MONITOR_HOST, monitor_port: int = MONITOR_PORT,
            **kwargs):
        """
        Runs your bot with Curio with the monitor enabled.

        :param token: The token to run with.
        :param shards: The number of shards to run.
            If this is None, the bot will autoshard.
            
        :param monitor_host: The host of the Curio monitor to use.
        :param monitor_port: The port of the Curio monitor to use.
        """
        if token is not None:
            self._token = token

        if not self.bot_type & BotType.BOT and shards != 1:
            raise CuriousError("Cannot start user bots in sharded mode")

        kernel = curio.Kernel()
        monitor = Monitor(kernel, monitor_host, monitor_port)
        if shards == AUTOSHARD or shards is None:
            coro = self.start_autosharded(token, **kwargs)
        else:
            coro = self.start(shards=shards, **kwargs)

        try:
            return kernel.run(coro, shutdown=True)
        except (KeyboardInterrupt, EOFError):
            kernel._crashed = False
            return kernel.run(self._cleanup())

    @classmethod
    def from_token(cls, token: str = None):
        """
        Starts a bot from a token object.

        :param token: The token to use for the bot.
        """
        bot = cls(token)
        return bot.run()
