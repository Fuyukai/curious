import collections
import curio
import logging

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

    def __init__(self, client):
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

        #: The state logger.
        self.logger = logging.getLogger("curious.state")

    def _reset(self):
        """
        Called after session is invalidated, to reset our state.
        """
        self._guilds = {}
        self._user = None
        self._session_id = None

        self._have_all_guilds.clear()

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

        # Don't fire `_ready` here, because we don't have all guilds.
        await self.client.fire_event("connect")

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

    def parse_message(self, event_data: dict):
        message = Message(self.client, **event_data)
        # discord won't give us the Guild object
        # so we have to search it from the channels
        # quick optimization - the default channel id == default guild ID
        # so if channel_id is in guilds, we can use `guild.default_channel`
        channel_id = int(event_data.get("channel_id"))
        if channel_id in self._guilds:
            channel = self._guilds[channel_id].default_channel
        else:
            try:
                channel = next(filter(lambda c: c.id == channel_id, self.get_all_channels()))
            except StopIteration:
                # no channel :(
                # don't fire events before we get all our data
                return

        author_id = int(event_data.get("author", {}).get("id", 0))

        message.channel = channel
        message.guild = channel.guild
        if message.guild:
            message.author = message.guild.get_member(author_id)

        return message

    async def handle_message_create(self, event_data: dict):
        """
        Called when MESSAGE_CREATE is dispatched.
        """
        message = self.parse_message(event_data)
        if not message:
            return

        await self.client.fire_event("message", message)

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
            # We've left this guild - clear i from our dictionary of guilds.
            guild = self._guilds.pop(guild_id, None)
            if guild:
                await self.client.fire_event("guild_leave", guild)

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
