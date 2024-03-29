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
from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from types import MappingProxyType
from typing import TYPE_CHECKING, Optional, Mapping, Iterable, Any, AsyncGenerator

import trio
from async_generator import aclosing

from curious.core import chunker as md_chunker
from curious.core.event import EventContext, EventManager, event as ev_dec, scan_events
# from curious.core.gateway import GatewayHandler, open_websocket
from curious.core.gateway import GatewayHandler
from curious.core.httpclient import HTTPClient, open_http_client
from curious.core.state import State
from curious.dataclasses.appinfo import AppInfo
from curious.dataclasses.bases import allow_external_makes
from curious.dataclasses.channel_type import ChannelType
from curious.dataclasses.invite import Invite
from curious.dataclasses.message import CHANNEL_REGEX, EMOJI_REGEX, MENTION_REGEX
from curious.dataclasses.presence import Game, Status
from curious.dataclasses.user import BotUser, User
from curious.dataclasses.webhook import Webhook
from curious.util import base64ify

if TYPE_CHECKING:
    from curious.dataclasses.guild import Guild
    from curious.dataclasses.channel import Channel

logger = logging.getLogger("curious.core.client")


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
    IGNORE_READY = ["connect", "guild_streamed", "guild_chunk", "guild_available", "guild_sync"]

    def __init__(
        self,
        token: str,
        http: HTTPClient,
        nursery: trio.Nursery,
    ):
        """
        :param token: The current token for this bot.
        """
        self._token: str = token
        self.shard_count: int = 0
        self.state = State(self)
        self.events = EventManager(nursery)

        #: The mapping of `shard_id -> gateway` objects.
        self._gateways = {}  # type: typing.MutableMapping[int, GatewayHandler]

        #: The current :class:`.Chunker` for this bot.
        self.chunker = md_chunker.Chunker(self)
        self.chunker.register_events(self.events)

        self._ready_state = {}

        #: The :class:`.HTTPClient` used for this bot.
        self.http = http

        #: The cached gateway URL.
        self._gw_url = None  # type: str

        #: The application info for this bot. Instance of :class:`.AppInfo`.
        #: This will be None for user bots.
        self.application_info = None  # type: AppInfo

        #: The task manager used for this bot.
        self.nursery = nursery

        for (name, event) in scan_events(self):
            self.events.add_event(event)

    @property
    def user(self) -> BotUser:
        """
        :return: The :class:`.User` that this client is logged in as.
        """
        return self.state._user

    @property
    def guilds(self) -> Mapping[int, Guild]:
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
            self.application_info.client_id
        )

    # @property
    # def events_handled(self) -> collections.Counter:
    #     """
    #     A :class:`collections.Counter` of all events that have been handled since the bot's bootup.
    #     This can be used to track statistics for events.
    #
    #     .. code-block:: python3
    #
    #         @command()
    #         async def events(self, ctx: Context):
    #             '''
    #             Shows the most common events.
    #             '''
    #
    #             ev = ctx.bot.events_handled.most_common(3)
    #             await ctx.channel.messages.send(", ".join("{}: {}".format(*x) for x in ev)
    #
    #     """
    #
    #     c = collections.Counter()
    #     for gw in self._gateways.values():
    #         c.update(gw._dispatches_handled)
    #
    #     return c

    @property
    def gateways(self) -> Mapping[int, GatewayHandler]:
        """
        :return: A read-only view of the current gateways for this client.
        """
        return MappingProxyType(self._gateways)

    def find_channel(self, channel_id: int) -> Optional[Channel]:
        """
        Finds a channel by channel ID.
        """
        return self.state.find_channel(channel_id)

    def guilds_for(self, shard_id: int) -> Iterable[Guild]:
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
    def fire_event(self, event_name: str, *args, **kwargs):
        """
        Fires an event.

        This actually passes the arguments to :meth:`.EventManager.fire_event`.
        """
        gateway = kwargs.get("gateway")
        if not self.state.is_ready(gateway.info.shard_id):
            if event_name not in self.IGNORE_READY and not event_name.startswith("gateway_"):
                return

        return self.events.fire_event(event_name, *args, **kwargs, client=self)

    async def wait_for(self, *args, **kwargs) -> Any:
        """
        Shortcut for :meth:`.EventManager.wait_for`.
        """
        return await self.events.wait_for(*args, **kwargs)

    # Gateway functions
    async def change_status(
        self,
        game: Game = None,
        status: Status = Status.ONLINE,
        afk: bool = False,
        shard_id: int = 0,
    ):
        """
        Changes the bot's current status.

        :param game: The game object to use. None for no game.
        :param status: The new status. Must be a :class:`.Status` object.
        :param afk: Is the bot AFK? Only useful for userbots.
        :param shard_id: The shard to change your status on.
        """

        gateway = self._gateways[shard_id]
        return await gateway.send_status(
            name=game.name if game else None,
            type_=game.type if game else None,
            url=game.url if game else None,
            status=status.value,
            afk=afk,
        )

    # HTTP Functions
    async def edit_profile(self, *, username: str = None, avatar: bytes = None):
        """
        Edits the profile of this bot.

        The user is **not** edited in-place - instead, you must wait for the `USER_UPDATE` event to
        be fired on the websocket.

        :param username: The new username of the bot.
        :param avatar: The bytes-like object that represents the new avatar you wish to use.
        """
        if username:
            if any(x in username for x in ("@", ":", "```")):
                raise ValueError("Username must not contain banned characters")

            if username in ("discordtag", "everyone", "here"):
                raise ValueError("Username cannot be a banned username")

            if not 2 <= len(username) <= 32:
                raise ValueError("Username must be 2-32 characters")

        if avatar:
            avatar = base64ify(avatar)

        await self.http.edit_user(username, avatar)

    async def edit_avatar(self, path: str):
        """
        A higher-level way to change your avatar.
        This allows you to provide a path to the avatar file instead of having to read it in
        manually.

        :param path: The path-like object to the avatar file.
        """
        with open(path, "rb") as f:
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

    async def get_application(self, application_id: int = None) -> AppInfo:
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

    async def get_invite(self, invite_code: str, *, with_counts: bool = True) -> Invite:
        """
        Gets an invite by code.

        :param invite_code: The invite code to get.
        :param with_counts: Return the approximate counts for this invite?
        :return: A new :class:`.Invite` object.
        """
        return Invite(self, **(await self.http.get_invite(invite_code, with_counts=with_counts)))

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
                if channel is None or channel.type not in [
                    ChannelType.TEXT,
                    ChannelType.VOICE,
                ]:
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
            with allow_external_makes():
                result = handler(ctx.gateway, dispatch)

                if inspect.isawaitable(result):
                    results = [await result]
                elif inspect.isasyncgen(result):
                    results = [r async for r in result]
                else:
                    results = [result]

            for item in results:
                if not isinstance(item, tuple):
                    self.events.fire_event(item, gateway=ctx.gateway, client=self)
                else:
                    self.events.fire_event(item[0], *item[1:], gateway=ctx.gateway, client=self)

        except Exception:
            logger.exception(f"Error decoding event {name} with data {dispatch}!")
            await self.kill()
            raise

    @ev_dec(name="ready")
    async def handle_ready(self, ctx: "EventContext"):
        """
        Handles a READY event, dispatching a ``shards_ready`` event when all shards are ready.
        """
        self._ready_state[ctx.shard_id] = True

        if not all(self._ready_state.values()):
            return

        self.events.fire_event("shards_ready", gateway=self._gateways[ctx.shard_id], client=self)

    async def _run_shard(self, shard_id: int, shard_count: int):
        """
        Handles a shard.

        :param shard_id: The shard ID to boot and handle.
        :param shard_count: The shard count to send in the identify packet.
        """
        # consume events
        gateway = GatewayHandler(
            token=self._token,
            gateway_url=self._gw_url,
            shard_id=shard_id,
            shard_count=shard_count,
        )

        self._gateways[shard_id] = gateway

        async with aclosing(gateway.read_events()) as agen:
            async for event in agen:
                self.fire_event(event[0], *event[1:], gateway=gateway)

    async def _spawn_shards(self, shard_count: int):
        """
        Starts the bot.

        :param shard_count: The number of shards to boot.
        """
        async with trio.open_nursery() as n:
            for shard_id in range(0, shard_count):
                self._ready_state[shard_id] = False
                n.start_soon(self._run_shard, shard_id, shard_count)

    async def _run_async(self) -> None:
        """
        Runs the client asynchronously.
        """
        url, shard_count = await self.http.get_shard_count()

        self.application_info = await self.get_application(None)

        self._gw_url = url
        self.shard_count = shard_count
        try:
            await self._spawn_shards(shard_count)
        finally:
            with trio.fail_after(1) as scope:
                scope.shield = True
                await self.kill()

    async def kill(self) -> None:
        """
        Kills the bot by closing all shards.
        """
        for gateway in self._gateways.copy().values():
            await gateway.kill(code=1006, reason="Bot killed")


@asynccontextmanager
async def open_client(token: str) -> AsyncGenerator[Client]:
    """
    Opens a new Discord client, connecting using the specified token.
    """

    async with trio.open_nursery() as n:
        async with open_http_client(token) as http:
            client = Client(token, http, n)
            yield client
            await client._run_async()

        n.cancel_scope.cancel()
