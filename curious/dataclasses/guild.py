import typing
from math import ceil

import curio

from curious import client
from curious.dataclasses import channel
from curious.dataclasses import member
from curious.dataclasses import user as dt_user
from curious.dataclasses.bases import Dataclass
from curious.dataclasses import role
from curious.dataclasses.status import Game
from curious.util import AsyncIteratorWrapper


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
    def channels(self) -> 'typing.Iterable[channel.Channel]':
        return self._channels.values()

    @property
    def members(self) -> 'typing.Iterable[member.Member]':
        return self._members.values()

    @property
    def roles(self) -> 'typing.Iterable[role.Role]':
        return self._roles.values()

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

    @property
    def default_role(self) -> 'role.Role':
        """
        :return: The default role for this guild.
        """
        return self._roles[self.id]

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

    @property
    def bans(self) -> 'typing.AsyncIterator[dt_user.User]':
        return AsyncIteratorWrapper(self._bot, self.get_bans())

    # Guild methods.
    async def leave(self):
        """
        Leaves the guild.
        """
        await self._bot.http.leave_guild(self.id)

    async def get_bans(self) -> 'typing.List[dt_user.User]':
        """
        Gets the bans for this guild.
        :return: A list of User objects, one for each ban.
        """
        bans = await self._bot.http.get_bans(self.id)
        users = []

        for user_data in bans:
            # TODO: Audit log stuff, if it ever comes out.
            user_data = user_data.get("user", None)
            users.append(dt_user.User(self._bot, **user_data))

        return users

    async def kick(self, victim: 'member.Member'):
        """
        Kicks somebody from the guild.

        :param victim: The member to kick.
        """
        victim_id = victim.user.id

        await self._bot.http.kick_member(self.id, victim_id)

    async def ban(self, victim: 'typing.Union[member.Member, user.User]', *,
                  delete_message_days: int=7):
        """
        Bans somebody from the guild.

        This can either ban a Member, in which they must be in the guild. Or this can ban a User, which does not need
        to be in the guild.

        Example for banning a member:

        .. code:: python
            member = guild.get_member(80528701850124288)
            await guild.ban(member)

        Example for banning a user:

        .. code:: python
            user = await client.get_user(80528701850124288)
            await guild.ban(user)

        :param victim: The person to ban.
        :param delete_message_days: The number of days to delete messages.
        """
        if isinstance(victim, member.Member):
            if victim.guild != self:
                raise ValueError("Member must be from this guild (try `member.user` instead)")

            victim_id = victim.user.id

        elif isinstance(victim, dt_user.User):
            victim_id = victim.id

        else:
            raise TypeError("Victim must be a Member or a User")

        await self._bot.http.ban_user(guild_id=self.id, user_id=victim_id, delete_message_days=delete_message_days)

    async def unban(self, user: 'dt_user.User'):
        """
        Unbans a user from this guild.

        Example for unbanning the first banned user:

        .. code:: python
            user = next(await guild.get_bans())
            await guild.unban(user)

        To unban an arbitrary user, use :meth:`Client.get_user`.

        .. code:: python
            user = await client.get_user(80528701850124288)
            await guild.unban(user)

        :param user: The user to forgive and unban.
        """
        forgiven_id = user.id

        await self._bot.http.unban_user(self.id, forgiven_id)
