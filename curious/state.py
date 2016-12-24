import collections
import typing

import curio
import logging

from curious.dataclasses.channel import Channel
from curious.dataclasses.guild import Guild
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.status import Game
from curious.dataclasses.user import User
from curious import gateway


class State(object):
    """
    This represents the state of the Client - in other libraries, the cache.

    It is also used to parse objects into their representations.
    """

    def __init__(self, client, max_messages: int = 500):
        #: The guilds the bot can see.
        self._guilds = {}

        #: The current user of this bot.
        #: This is automatically set after login.
        self._user = None

        #: The client associated with this connection.
        self.client = client

        #: The session ID of this connection.
        self._session_id = None

        #: Have we got all guilds?
        #: This is set once all guilds have received a GUILD_CREATE, and are no longer unavailable.
        self._have_all_guilds = curio.Event()

        #: Has ready been reached at least once?
        #: This will signal that in GUILD_CREATE, we need to dispatch to `on_guild_join`.
        self._is_ready = curio.Event()

        #: The private channel cache.
        self._private_channels = {}

        #: The state logger.
        self.logger = logging.getLogger("curious.state")

        #: The deque of messages.
        #: This is bounded to prevent the message cache from growing infinitely.
        self._messages = collections.deque(maxlen=max_messages)

    def _reset(self):
        """
        Called after session is invalidated, to reset our state.
        """
        self._guilds = {}
        self._user = None
        self._session_id = None

        self._have_all_guilds.clear()
        self._messages.clear()

    async def _check_all_guilds(self):
        """
        Checks to make sure all guilds are here.

        This will ensure all guilds are not marked `unavailable`.
        """
        have_all = all(guild.unavailable is False for guild in self._guilds.values())
        if have_all:
            await self._have_all_guilds.set()

        return have_all or self._have_all_guilds.set()

    @property
    def guilds(self):
        return self._guilds.values()

    @property
    def have_all_chunks(self):
        return all(guild._finished_chunking.is_set() for guild in self.guilds)

    # get_all_* methods
    def get_all_channels(self):
        for guild in self._guilds.values():
            for channel in guild.channels:
                yield channel

    def _get_channel(self, channel_id: int) -> Channel:
        # default channel_id == guild id
        if channel_id in self._guilds:
            try:
                return self._guilds[channel_id].default_channel
            except KeyError:
                return None

        if channel_id in self._private_channels:
            return self._private_channels[channel_id]

        for channel in self.get_all_channels():
            if channel.id == channel_id:
                return channel

    def _find_message(self, message_id: int) -> Message:
        for message in reversed(self._messages):
            if message.id == message_id:
                return message

    def new_private_channel(self, channel_data: dict) -> Channel:
        """
        Creates a new private channel and caches it.

        :param channel_data: The channel data to cache.
        """
        channel = Channel(self.client, **channel_data)
        self._private_channels[channel.id] = channel

        return channel

    # Event handlers.
    # These parse the events and deconstruct them.
    async def handle_ready(self, event_data: dict):
        """
        Called when READY is dispatched.
        """
        self._session_id = event_data.get("session_id")

        # Create our bot user.
        self._user = User(self.client, **event_data.get("user"))

        # Create all of the guilds.
        for guild in event_data.get("guilds"):
            new_guild = Guild(self.client, **guild)
            self._guilds[new_guild.id] = new_guild

        # Create all of the private channels.
        for channel in event_data.get("private_channels"):
            self.new_private_channel(channel)

        # Don't fire `_ready` here, because we don't have all guilds.
        await self.client.fire_event("connect")

        # However, if the client has no guilds, we DO want to fire ready.
        if len(self._guilds) == 0:
            await self.client.fire_event("ready")

    async def handle_resumed(self, event_data: dict):
        self.logger.info("Successfully resumed session from a previous connection.")
        await self.client.fire_event("resumed")

    async def handle_presence_update(self, event_data: dict):
        """
        Called when a member changes game.
        """
        guild_id = int(event_data.get("guild_id"))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member_id = int(event_data["user"]["id"])
        member = guild.get_member(member_id)

        if member is None:
            # thanks discord
            return

        old_member = member._copy()

        game = event_data.get("game", {})
        if game is None:
            game = {}

        member.game = Game(**game, status=event_data.get("status"))
        member.status = event_data.get("status")

        await self.client.fire_event("member_update", old_member, member)

    async def handle_guild_members_chunk(self, event_data: dict):
        """
        Called when a chunk of members has arrived.
        """
        id = int(event_data.get("guild_id"))
        guild = self._guilds.get(id)

        if not guild:
            self.logger.warning("Got a chunk for a Guild that doesn't exist...")
            return

        members = event_data.get("members", [])
        self.logger.info("Got a chunk of {} members in guild {}".format(len(members), guild.name or guild.id))

        guild._handle_member_chunk(event_data.get("members"))

        if guild._chunks_left <= 0:
            # Set the finished chunking event.
            await guild._finished_chunking.set()

        # Check if we have all chunks.
        if not self._is_ready.is_set() and self.have_all_chunks:
            # Dispatch our `on_ready`.
            await self._is_ready.set()
            await self.client.fire_event("ready")

    async def handle_guild_create(self, event_data: dict):
        """
        Called when GUILD_CREATE is dispatched.
        """
        id = int(event_data.get("id"))
        guild = self._guilds.get(id)

        had_guild = True
        if guild:
            guild.from_guild_create(**event_data)
        else:
            had_guild = False
            guild = Guild(self.client, **event_data)
            self._guilds[guild.id] = guild

        # Dispatch the new event before we start chunking.
        if self._is_ready.is_set():
            if had_guild:
                await self.client.fire_event("guild_available", guild)
            else:
                # We didn't have it before, so we just joined it.
                # Hence, we fire a `guild_join` event.
                await self.client.fire_event("guild_join", guild)

        # Request all members from the guild.
        raise gateway.ChunkGuild(guild)

    async def handle_guild_delete(self, event_data: dict):
        """
        Called when a guild becomes unavailable.
        """
        guild_id = int(event_data.get("id", 0))
        # Check if the `unavailable` flag is there.
        # If it is, we want to semi-discard this event, because all it means is the guild becomes unavailable.
        if event_data.get("unavailable", False):
            # Set the guild to unavailable, but don't delete it.
            guild = self._guilds.get(guild_id)
            if guild:
                guild.unavailable = True
                await self.client.fire_event("guild_unavailable", guild)

        else:
            # We've left this guild - clear it from our dictionary of guilds.
            guild = self._guilds.pop(guild_id, None)
            if guild:
                await self.client.fire_event("guild_leave", guild)

    def parse_message(self, event_data: dict, cache: bool = True) -> Message:
        message = Message(self.client, **event_data)
        # discord won't give us the Guild id
        # so we have to search it from the channels
        channel_id = int(event_data.get("channel_id"))
        channel = self._get_channel(channel_id)
        if not channel:
            # fuck off discord
            return None

        author_id = int(event_data.get("author", {}).get("id", 0))

        message.channel = channel
        message.guild = channel.guild
        if message.channel.is_private:
            message.author = message.channel.user
        else:
            message.author = message.guild.get_member(author_id)

        if cache:
            self._messages.append(message)

        return message

    async def handle_message_create(self, event_data: dict):
        """
        Called when MESSAGE_CREATE is dispatched.
        """
        message = self.parse_message(event_data)
        if not message:
            return

        # Hope that messages are ordered!
        message.channel._last_message_id = message.id

        await self.client.fire_event("message_create", message)

    async def handle_message_update(self, event_data: dict):
        """
        Called when MESSAGE_UPDATE is dispatched.
        """
        new_message = self.parse_message(event_data, cache=False)
        if not new_message:
            return

        # Try and find the old message.
        old_message = self._find_message(new_message.id)
        if not old_message:
            return

        self._messages.remove(old_message)
        self._messages.append(new_message)

        if old_message.content != new_message.content:
            # Fire a message_edit, as well as a message_update, because the content differs.
            await self.client.fire_event("message_edit", old_message, new_message)

        await self.client.fire_event("message_update", old_message, new_message)

    async def handle_message_delete(self, event_data: dict):
        """
        Called when MESSAGE_DELETE is dispatched.
        """
        message_id = int(event_data.get("id"))
        message = self._find_message(message_id)

        if not message:
            return

        await self.client.fire_event("message_delete", message)

    async def handle_message_delete_bulk(self, event_data: dict):
        """
        Called when MESSAGE_DELETE_BULK is dispatched.
        """
        messages = []
        for message in event_data.get("ids", []):
            message = self._find_message(int(message))
            if not message:
                continue

            messages.append(message)

        await self.client.fire_event("message_delete_bulk", messages)

    async def handle_guild_member_add(self, event_data: dict):
        """
        Called when a guild adds a new member.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member = Member(self.client, **event_data)
        member.guild = guild

        guild._members[member.id] = member
        await self.client.fire_event("member_join", member)

    async def handle_guild_member_remove(self, event_data: dict):
        """
        Called when a guild removes a member.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member = guild._members.pop(int(event_data["user"]["id"]), None)
        if not member:
            # We can't see the member, so don't fire an event for it.
            return

        await self.client.fire_event("member_leave", member)

    async def handle_guild_member_update(self, event_data: dict):
        """
        Called when a guild member is updated.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member_id = int(event_data["user"]["id"])
        member = guild.get_member(member_id)

        if not member:
            return

        # Make a copy of the member for the old previous reference.
        old_member = member._copy()
        member.user = User(self.client, **event_data["user"])

        for role_id in event_data.get("roles", []):
            role_id = int(role_id)
            role = guild.get_role(role_id)

            if not role:
                # thanks discord
                continue

            member._roles[role.id] = role

        guild._members[member.id] = member

        member.nickname = event_data.get("nickname")
        await self.client.fire_event("member_update", old_member, member)

    async def handle_guild_ban_add(self, event_data: dict):
        """
        Called when a ban is added to a guild.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if guild is None:
            return

        member_id = int(event_data["user"]["id"])
        member = guild.get_member(member_id)

        if not member:
            # Dispatch to `user_ban` instead of `member_ban`.
            user = User(self.client, **event_data["user"])
            await self.client.fire_event("user_ban", guild, user)
            return

        await self.client.fire_event("member_ban", member)

    async def handle_guild_ban_remove(self, event_data: dict):
        """
        Called when a ban is removed from a guild.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if guild is None:
            return

        user = User(self.client, **event_data["user"])
        await self.client.fire_event("user_unban", guild, user)

    async def handle_channel_create(self, event_data: dict):
        """
        Called when a channel is created.
        """
        channel = Channel(self.client, **event_data)
        if channel.is_private:
            self._private_channels[channel.id] = channel

        else:
            guild_id = int(event_data.get("guild_id"))
            guild = self._guilds.get(guild_id)

            if not guild:
                return

            channel.guild = guild

        await self.client.fire_event("channel_create", channel)

    async def handle_channel_update(self, event_data: dict):
        """
        Called when a channel is updated.
        """
        channel_id = int(event_data.get("id"))
        channel = self._get_channel(channel_id)

        if not channel:
            return

        old_channel = channel._copy()

        channel.name = event_data.get("name", channel.name)
        channel.position = event_data.get("position", channel.position)
        channel.topic = event_data.get("topic", channel.topic)

        # TODO: Permission overwrites.
        await self.client.fire_event("channel_update", old_channel, channel)

    async def handle_channel_delete(self, event_data: dict):
        """
        Called when a channel is deleted.
        """
        channel_id = int(event_data.get("channel_id", 0))
        channel = self._get_channel(channel_id)

        if channel.is_private:
            del self._private_channels[channel.id]
        else:
            del channel.guild._channels[channel.id]

        await self.client.fire_event("channel_delete", channel)

    async def handle_typing_start(self, event_data: dict):
        """
        Called when a user starts typing.
        """
        member_id = int(event_data.get("user_id"))
        channel_id = int(event_data.get("channel_id"))

        channel = self._get_channel(channel_id)
        if not channel:
            return

        if not channel.is_private:
            member = channel.guild.get_member(member_id)
            if not member:
                return
        else:
            member = channel.user

        await self.client.fire_event("user_typing", channel, member)
