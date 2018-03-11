# This file is part of curious.
#
# curious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# curious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with curious.  If not, see <http://www.gnu.org/licenses/>.

"""
The main client class.

This contains a definition for :class:`.Client` which is used to interface primarily with Discord.

.. currentmodule:: curious.core.client
"""

import collections
import enum
import functools
import inspect
import logging
import typing
from types import MappingProxyType

import multio

from curious.core import chunker as md_chunker
from curious.core.event import EventContext, EventManager, event as ev_dec, scan_events
from curious.core.gateway import GatewayHandler, open_websocket
from curious.core.httpclient import HTTPClient
from curious.dataclasses import channel as dt_channel, guild as dt_guild, member as dt_member
from curious.dataclasses.appinfo import AppInfo
from curious.dataclasses.invite import Invite
from curious.dataclasses.message import CHANNEL_REGEX, EMOJI_REGEX, MENTION_REGEX
from curious.dataclasses.presence import Game, Status
from curious.dataclasses.user import BotUser, User
from curious.dataclasses.webhook import Webhook
from curious.dataclasses.widget import Widget
from curious.util import base64ify

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

    To start, you can create an instance of the client by passing it the token you want to use:

    .. code-block:: python3

        cl = Client("my.token.string")

    Registering events can be done with the :meth:`.Client.event` decorator, or alternatively
    manual usage of the :class:`.EventHandler` on :attr:`.Client.events`.

    .. code-block:: python3

        @cl.event("ready")
        async def loaded(ctx: EventContext):
            print("Bot logged in.")

    """
    #: A list of events to ignore the READY status.
    IGNORE_READY = [
        "connect",
        "guild_streamed",
        "guild_chunk",
        "guild_available",
        "guild_sync"
    ]

    def __init__(self, token: str, *,
                 state_klass: type = None,
                 bot_type: int = (BotType.BOT | BotType.ONLY_USER)):
        """
        :param token: The current token for this bot.
        :param state_klass: The class to construct the connection state from.
        :param bot_type: A union of :class:`.BotType` that defines the type of this bot.
        """
        #: The mapping of `shard_id -> gateway` objects.
        self._gateways = {}  # type: typing.MutableMapping[int, GatewayHandler]

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
        #: The current :class:`.Chunker` for this bot.
        self.chunker = md_chunker.Chunker(self)
        self.chunker.register_events(self.events)

        self._ready_state = {}

        #: The :class:`.HTTPClient` used for this bot.
        self.http = HTTPClient(self._token, bot=bool(self.bot_type & BotType.BOT))

        #: The cached gateway URL.
        self._gw_url = None  # type: str

        #: The application info for this bot. Instance of :class:`.AppInfo`.
        #: This will be None for user bots.
        self.application_info = None  # type: AppInfo

        #: The task manager used for this bot.
        self.task_manager = None

        for (name, event) in scan_events(self):
            self.events.add_event(event)

    @property
    def user(self) -> BotUser:
        """
        :return: The :class:`.User` that this client is logged in as.
        """
        return self.state._user

    @property
    def guilds(self) -> 'typing.Mapping[int, dt_guild.Guild]':
        """
        :return: A mapping of int -> :class:`.Guild` that this client can see.
        """
        return self.state.guilds

    @property
    def invite_url(self) -> str:
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
                await ctx.channel.messages.send(", ".join("{}: {}".format(*x) for x in ev)
        
        """

        c = collections.Counter()
        for gw in self._gateways.values():
            c.update(gw._dispatches_handled)

        return c

    @property
    def gateways(self) -> 'typing.Mapping[int, GatewayHandler]':
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
            return func

        return _inner

    # rip in peace old fire_event
    # 2016-2017
    # broke my pycharm
    async def fire_event(self, event_name: str, *args, **kwargs):
        """
        Fires an event.

        This actually passes the arguments to :meth:`.EventManager.fire_event`.
        """
        gateway = kwargs.get("gateway")
        if not self.state.is_ready(gateway.gw_state.shard_id):
            if event_name not in self.IGNORE_READY and not event_name.startswith("gateway_"):
                return

        return await self.events.fire_event(event_name, *args, **kwargs, client=self)

    async def wait_for(self, *args, **kwargs) -> typing.Any:
        """
        Shortcut for :meth:`.EventManager.wait_for`.
        """
        return await self.events.wait_for(*args, **kwargs)

    # Gateway functions
    async def change_status(self, game: Game = None, status: Status = Status.ONLINE,
                            afk: bool = False,
                            shard_id: int = 0):
        """
        Changes the bot's current status.

        :param game: The game object to use. None for no game.
        :param status: The new status. Must be a :class:`.Status` object.
        :param afk: Is the bot AFK? Only useful for userbots.
        :param shard_id: The shard to change your status on.
        """

        gateway = self._gateways[shard_id]
        return await gateway.send_status(
            name=game.name if game else None, type_=game.type if game else None,
            url=game.url if game else None,
            status=status.value, afk=afk
        )

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

            if username in ("discordtag", "everyone", "here"):
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
        :return: A new :class:`.User` object.
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
        :return: A new :class:`.AppInfo` object corresponding to the application.
        """
        data = await self.http.get_app_info(application_id=application_id)
        appinfo = AppInfo(self, **data)

        return appinfo

    async def get_webhook(self, webhook_id: int) -> Webhook:
        """
        Gets a webhook by ID.

        :param webhook_id: The ID of the webhook to get.
        :return: A new :class:`.Webhook` object.
        """
        return self.state.make_webhook(await self.http.get_webhook(webhook_id))

    async def get_invite(self, invite_code: str, *,
                         with_counts: bool = True) -> Invite:
        """
        Gets an invite by code.

        :param invite_code: The invite code to get.
        :param with_counts: Return the approximate counts for this invite?
        :return: A new :class:`.Invite` object.
        """
        return Invite(self, **(await self.http.get_invite(invite_code, with_counts=with_counts)))

    async def get_widget(self, guild_id: int) -> Widget:
        """
        Gets a widget from a guild.
        
        :param guild_id: The ID of the guild to get the widget of. 
        :return: A :class:`.Widget` object.
        """
        data = await self.http.get_widget_data(guild_id)
        return Widget(self, **data)

    async def clean_content(self, content: str) -> str:
        """
        Cleans the content of a message, using the bot's cache.

        :param content: The content to clean.
        :return: The cleaned up message.
        """
        final = []
        tokens = content.split(" ")
        # o(2n) loop
        for token in tokens:
            # try and find a channel from public channels
            channel_match = CHANNEL_REGEX.match(token)
            if channel_match is not None:
                channel_id = int(channel_match.groups()[0])
                channel = self.state.find_channel(channel_id)
                if channel is None or channel.type not in \
                        [dt_channel.ChannelType.TEXT, dt_channel.ChannelType.VOICE]:
                    final.append("#deleted-channel")
                else:
                    final.append(f"#{channel.name}")

                continue

            user_match = MENTION_REGEX.match(token)
            if user_match is not None:
                found_name = None
                user_id = int(user_match.groups()[0])
                member_or_user = self.state.find_member_or_user(user_id)
                if member_or_user:
                    found_name = member_or_user.name

                if found_name is None:
                    final.append(token)
                else:
                    final.append(f"@{found_name}")

                continue

            emoji_match = EMOJI_REGEX.match(token)
            if emoji_match is not None:
                final.append(f":{emoji_match.groups()[0]}:")
                continue

            # if we got here, matching failed
            # so just add the token
            final.append(token)

        return " ".join(final)

    # download_ methods
    async def download_guild_member(self, guild_id: int, member_id: int) -> 'dt_member.Member':
        """
        Downloads a :class:`.Member` over HTTP.
        
        .. warning::
            
            The :attr:`.Member.roles` and similar fields will be empty when downloading a Member,
            unless the guild was in cache.
        
        :param guild_id: The ID of the guild which the member is in. 
        :param member_id: The ID of the member to get.
        :return: The :class:`.Member` object downloaded.
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
        Downloads the members for a :class:`.Guild` over HTTP.
        
        .. warning::
        
            This can take a long time on big guilds.
        
        :param guild_id: The ID of the guild to download members for.
        :param after: The member ID after which to get members for.
        :param limit: The maximum number of members to return. By default, this is 1000 members.
        :param get_all: Should *all* members be fetched?
        :return: An iterable of :class:`.Member`.
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
        Downloads all the :class:`.Channel` for a Guild.
        
        :param guild_id: The ID of the guild to download channels for. 
        :return: An iterable of :class:`.Channel` objects.
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
        Downloads a :class:`.Guild` over HTTP.
        
        .. warning::
        
            If ``full`` is True, this will fetch and fill ALL objects of the guild, including 
            channels and members. This can take a *long* time if the guild is large.
        
        :param guild_id: The ID of the Guild object to download. 
        :param full: If all extra data should be downloaded alongside it.
        :return: The :class:`.Guild` object downloaded.
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

    @ev_dec(name="gateway_dispatch_received")
    async def handle_dispatches(self, ctx: EventContext, name: str, dispatch: dict):
        """
        Handles dispatches for the client.
        """
        try:
            handle_name = name.lower()
            handler = getattr(self.state, f"handle_{handle_name}")
        except AttributeError:
            logger.warning(f"Got unknown dispatch {name}")
            return
        else:
            logger.debug(f"Processing event {name}")

        try:
            result = handler(ctx.gateway, dispatch)

            if inspect.isawaitable(result):
                result = await result
            elif inspect.isasyncgen(result):
                async with multio.asynclib.finalize_agen(result) as gen:
                    async for i in gen:
                        await self.events.fire_event(i[0], *i[1:], gateway=ctx.gateway, client=self)

                # no more processing after the async gen
                return

            if not isinstance(result, tuple):
                await self.events.fire_event(result, gateway=ctx.gateway, client=self)
            else:
                await self.events.fire_event(result[0], *result[1:], gateway=ctx.gateway,
                                             client=self)

        except Exception:
            logger.exception(f"Error decoding event {name} with data {dispatch}!")
            await self.kill()
            raise

    @ev_dec(name="ready")
    async def handle_ready(self, ctx: 'EventContext'):
        """
        Handles a READY event, dispatching a ``shards_ready`` event when all shards are ready.
        """
        self._ready_state[ctx.shard_id] = True

        if not all(self._ready_state.values()):
            return

        await self.events.fire_event("shards_ready", gateway=self._gateways[ctx.shard_id],
                                     client=self)

    async def handle_shard(self, shard_id: int, shard_count: int):
        """
        Handles a shard.

        :param shard_id: The shard ID to boot and handle.
        :param shard_count: The shard count to send in the identify packet.
        """
        # consume events
        async with open_websocket(self._token, self._gw_url,
                                  shard_id=shard_id, shard_count=shard_count) as gw:
            self._gateways[shard_id] = gw

            try:
                async with multio.asynclib.finalize_agen(gw.events()) as agen:
                    async for event in agen:
                        await self.fire_event(event[0], *event[1:], gateway=gw)
            except Exception as e:  # kill the bot if we failed to parse something
                await self.kill()
                raise
            finally:
                self._gateways.pop(shard_id, None)

    async def start(self, shard_count: int):
        """
        Starts the bot.

        :param shard_count: The number of shards to boot.
        """
        if self.bot_type & BotType.BOT:
            self.application_info = AppInfo(self, **(await self.http.get_app_info(None)))

        # update ready state
        for shard_id in range(shard_count):
            self._ready_state[shard_id] = False

        async with multio.asynclib.task_manager() as tg:
            self.task_manager = tg
            self.events.task_manager = tg

            for shard_id in range(0, shard_count):
                await multio.asynclib.spawn(tg, self.handle_shard, shard_id, shard_count)

    async def run_async(self, *, shard_count: int = 1, autoshard: bool = True):
        """
        Runs the client asynchronously.

        :param shard_count: The number of shards to boot.
        :param autoshard: If the bot should be autosharded.
        """
        if autoshard:
            shard_count = await self.get_shard_count()

        self.shard_count = shard_count
        return await self.start(shard_count)

    async def kill(self) -> None:
        """
        Kills the bot by closing all shards.
        """
        for gateway in self._gateways.values():
            await gateway.close(code=1006, reason="Bot killed", reconnect=False)

    def run(self, *, shard_count: int = 1, autoshard: bool = True, **kwargs):
        """
        Convenience method to run the bot with multio.

        :param shard_count: The number of shards to use. Ignored if autoshard is True.
        :param autoshard: If the bot should be autosharded.
        """

        p = functools.partial(self.run_async, shard_count=shard_count, autoshard=autoshard)
        multio.run(p, **kwargs)

    @classmethod
    def from_token(cls, token: str = None):
        """
        Starts a bot from a token object.

        :param token: The token to use for the bot.
        """
        bot = cls(token)
        return bot.run()
