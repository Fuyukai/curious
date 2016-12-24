from math import ceil

import curio

from curious import client
from curious.dataclasses import channel
from curious.dataclasses import member
from curious.dataclasses.bases import Dataclass
from curious.dataclasses import role
from curious.dataclasses.status import Game


class Guild(Dataclass):

    __slots__ = ("unavailable", "name", "_icon_hash", "_owner_id", "region", "_roles", "_members",
                 "_channels", "member_count", "large")

    def __init__(self, bot: 'client.Client', **kwargs):
        """
        Creates a new Guild object.
        """
        super().__init__(kwargs.pop("id"), bot)

        #: If the guild is unavailable or not.
        #: If this is True, many fields return `None`.
        self.unavailable = kwargs.pop("unavailable", False)

        # Placeholder values.
        #: The name of this guild.
        self.name = None  # type: str

        #: The icon hash of this guild.
        #: Used to construct the icon URL later.
        self._icon_hash = None  # type: str

        #: The owner ID of this guild.
        self._owner_id = None  # type: int

        #: The voice region of this guild.
        self.region = None  # type: str

        #: The roles that this guild has.
        self._roles = {}

        #: The members of this guild.
        self._members = {}

        #: The channels of this guild.
        self._channels = {}

        #: The number of numbers this guild has.
        #: This is automatically updated.
        self.member_count = 0  # type: int

        #: Is this guild a large guild?
        self.large = False  # type: bool

        #: Has this guild finished chunking?
        self._finished_chunking = curio.Event()
        self._chunks_left = 0

        self.from_guild_create(**kwargs)

    @property
    def channels(self):
        return self._channels.values()

    @property
    def members(self):
        return self._members.values()

    @property
    def owner(self) -> 'member.Member':
        return self._members[self._owner_id]

    @property
    def me(self) -> 'member.Member':
        return self._members[self._bot.user.id]

    @property
    def default_channel(self) -> 'channel.Channel':
        """
        :return: The default channel for this guild.
        """
        return self._channels[self.id]

    def get_member(self, member_id: int) -> 'member.Member':
        return self._members.get(member_id)

    def get_role(self, role_id: int) -> 'role.Role':
        return self._roles.get(role_id)

    def get_channel(self, channel_id: int) -> 'channel.Channel':
        return self._channels.get(channel_id)

    def start_chunking(self):
        self._finished_chunking.clear()
        self._chunks_left = ceil(self.member_count / 1000)

    async def wait_until_chunked(self):
        """
        Waits until the guild has finished chunking.

        Useful for when you join a big guild.
        """
        await self._finished_chunking.wait()

    def _handle_member_chunk(self, members: list):
        """
        Handles a chunk of members.
        """
        if self._chunks_left >= 1:
            # We have a new chunk, so decrement the number left.
            self._chunks_left -= 1

        for member_data in members:
            id = int(member_data["user"]["id"])
            if id in self._members:
                member_obj = self._members[id]
            else:
                member_obj = member.Member(self._bot, **member_data)
            for role_ in member_data.get("roles", []):
                role_obj = self._roles.get(int(role_))
                if role_obj:
                    member_obj._roles[role_obj.id] = role_obj

            member_obj.guild = self
            self._members[member_obj.id] = member_obj

    def from_guild_create(self, **data: dict) -> 'Guild':
        """
        Populates the fields from a GUILD_CREATE event.

        :param data: The GUILD_CREATE data to use.
        """
        self.unavailable = data.get("unavailable", True)

        if self.unavailable:
            # We can't use any of the extra data here, so don't bother.
            return self

        self.name = data.get("name")  # type: str
        self._icon_hash = data.get("icon")  # type: str
        self._owner_id = int(data.get("owner_id"))  # type: int
        self.large = data.get("large", False)

        self.member_count = data.get("member_count", 0)

        # Create all the Role objects for the server.
        for role_data in data.get("roles", []):
            role_obj = role.Role(self._bot, **role_data)
            role_obj.guild = self
            self._roles[role_obj.id] = role_obj

        # Create all the Member objects for the server.
        self._handle_member_chunk(data.get("members"))

        for presence in data.get("presences", []):
            member_id = int(presence["user"]["id"])
            member_obj = self._members.get(member_id)

            if not member_obj:
                continue

            game = presence.get("game", {})
            if game is None:
                game = {}

            if "status" in game:
                game.pop("status")

            member_obj.game = Game(**game, status=presence.get("status"))

        # Create all of the channel objects.
        for channel_data in data.get("channels", []):
            channel_obj = channel.Channel(self._bot, **channel_data)
            channel_obj.guild = self
            self._channels[channel_obj.id] = channel_obj

    # Guild methods.
    async def leave(self):
        """
        Leaves the guild.
        """
        await self._bot.http.leave_guild(self.id)
