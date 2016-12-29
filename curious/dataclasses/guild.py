import typing
from math import ceil

import curio

from curious import client
from curious.dataclasses import channel
from curious.dataclasses import member as dt_member
from curious.dataclasses import user as dt_user
from curious.dataclasses.bases import Dataclass
from curious.dataclasses import role
from curious.dataclasses.status import Game
from curious.event import EventContext
from curious.exc import PermissionsError, HierachyError
from curious.util import AsyncIteratorWrapper


class Guild(Dataclass):
    """
    :ivar unavailable: If this guild is unavailable or not.
    :ivar name: The name of this guild.
    :ivar region: The voice region of this guild.
    :ivar member_count: The number of members this guild has.
    """

    def __init__(self, bot: 'client.Client', **kwargs):
        """
        Creates a new Guild object.
        """
        super().__init__(kwargs.pop("id"), bot)

        #: If the guild is unavailable or not.
        #: If this is True, many fields return `None`.
        self.unavailable = kwargs.get("unavailable", False)

        # Placeholder values.
        #: The name of this guild.
        self.name = None  # type: str

        #: The icon hash of this guild.
        #: Used to construct the icon URL later.
        self._icon_hash = None  # type: str

        #: The owner ID of this guild.
        self._owner_id = None  # type: int

        #: The AFK channel ID of this guild.
        self._afk_channel_id = None  # type: int

        #: The AFK timeout for this guild.
        self.afk_timeout = None  # type: int

        #: The voice region of this guild.
        self.region = None  # type: str

        #: The MFA level of this guild.
        self.mfa_level = 0  # type: int

        #: The verification level of this guild.
        self.verification_level = 0  # type: int

        #: The shard ID this guild is associated with.
        self.shard_id = None

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

    def _copy(self):
        obb = object.__new__(self.__class__)

        obb.unavailable = self.unavailable
        obb.name = self.name
        obb._icon_hash = self._icon_hash
        obb._owner_id = self._owner_id
        obb.region = self.region
        obb.shard_id = self.shard_id
        obb._roles = self._roles.copy()
        obb._members = self._members.copy()
        obb._channels = self._members.copy()
        obb.member_count = self.member_count
        obb.large = self.large
        obb._afk_channel_id = self._afk_channel_id
        obb.afk_timeout = self.afk_timeout
        obb.mfa_level = self.mfa_level

        return obb

    @property
    def channels(self) -> 'typing.Iterable[channel.Channel]':
        """
        :return: A list of :class:`curious.dataclasses.channel.Channel` objects that represent the channels on this
        guild.
        """
        return self._channels.values()

    @property
    def members(self) -> 'typing.Iterable[dt_member.Member]':
        """
        :return: A list of :class:`curious.dataclasses.member.Member` objects that represent the members on this guild.
        """
        return self._members.values()

    @property
    def roles(self) -> 'typing.Iterable[role.Role]':
        """
        :return: A list of :class:`curious.dataclasses.role.Role` objects that represent the roles on this guild.
        """
        return self._roles.values()

    @property
    def owner(self) -> 'dt_member.Member':
        """
        :return: A :class:`curious.dataclasses.member.Member` object that represents the owner of this guild.
        """
        return self._members[self._owner_id]

    @property
    def me(self) -> 'dt_member.Member':
        """
        :return: A :class:`curious.dataclasses.member.Member` object that represents the current user in this guild.
        """
        return self._members[self._bot.user.id]

    @property
    def default_channel(self) -> 'channel.Channel':
        """
        :return: A :class:`curious.dataclasses.channel.Channel` object that represents the default channel of this
        guild.
        """
        return self._channels[self.id]

    @property
    def default_role(self) -> 'role.Role':
        """
        :return: A :class:`curious.dataclasses.role.Role` object that represents the default role of this
        guild.
        """
        return self._roles[self.id]

    @property
    def afk_channel(self) -> 'channel.Channel':
        """
        :return: A :class:`Channel` representing the AFK channel for this guild.
        """
        try:
            return self._channels[self._afk_channel_id]
        except IndexError:
            # the afk channel CAN be None
            return None

    def get_member(self, member_id: int) -> 'dt_member.Member':
        """
        Gets a member from the guild by ID.

        :param member_id: The member ID to lookup.
        :return: The :class:`curious.dataclasses.member.Member` object that represents the member, or None if they
        couldn't be found.
        """
        return self._members.get(member_id)

    def get_role(self, role_id: int) -> 'role.Role':
        """
        Gets a role from the guild by ID.

        :param role_id: The role ID to look up.
        :return: The :class:`curious.dataclasses.role.Role` object that represents the Role, or None if it couldn't
        be found.
        """
        return self._roles.get(role_id)

    def get_channel(self, channel_id: int) -> 'channel.Channel':
        """
        Gets a channel from the guild by ID.

        :param channel_id: The channel ID to look up.
        :return: The :class:`curious.dataclasses.channel.Channel` object that represents the Channel, or None if it
        couldn't be found.
        """
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
                member_obj = dt_member.Member(self._bot, **member_data)
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
        self.unavailable = data.pop("unavailable", False)

        if self.unavailable:
            # We can't use any of the extra data here, so don't bother.
            return self

        self.name = data.get("name")  # type: str
        self._icon_hash = data.get("icon")  # type: str
        self._owner_id = int(data.get("owner_id"))  # type: int
        self.large = data.get("large", False)
        self.region = data.get("region")
        afk_channel_id = data.get("afk_channel_id")
        if afk_channel_id:
            afk_channel_id = int(afk_channel_id)
        self._afk_channel_id = afk_channel_id
        self.afk_timeout = data.get("afk_timeout")
        self.verification_level = data.get("verification_level")
        self.mfa_level = data.get("mfa_level")

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

            member_obj.game = Game(**game)
            member_obj.status = presence.get("status")

        # Create all of the channel objects.
        for channel_data in data.get("channels", []):
            channel_obj = channel.Channel(self._bot, guild=self, **channel_data)
            channel_obj.guild = self
            self._channels[channel_obj.id] = channel_obj

    @property
    def bans(self) -> 'typing.AsyncIterator[dt_user.User]':
        return AsyncIteratorWrapper(self._bot, self.get_bans())

    @property
    def icon_url(self) -> str:
        """
        :return: The icon URL for this server.
        """
        return "https://cdn.discordapp.com/icons/{}/{}.jpg".format(self.id, self._icon_hash)

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
        if not self.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        bans = await self._bot.http.get_bans(self.id)
        users = []

        for user_data in bans:
            # TODO: Audit log stuff, if it ever comes out.
            user_data = user_data.get("user", None)
            users.append(dt_user.User(self._bot, **user_data))

        return users

    async def kick(self, victim: 'dt_member.Member'):
        """
        Kicks somebody from the guild.

        :param victim: The member to kick.
        """
        if not self.me.guild_permissions.ban_members:
            raise PermissionsError("kick_members")

        if victim.guild != self:
            raise ValueError("Member must be from this guild (try `member.user` instead)")

        if victim.top_role >= self.me.top_role:
            raise HierachyError("Top role is equal to or lower than victim's top role")

        victim_id = victim.user.id

        await self._bot.http.kick_member(self.id, victim_id)

    async def ban(self, victim: 'typing.Union[dt_member.Member, dt_user.User]', *,
                  delete_message_days: int=7):
        """
        Bans somebody from the guild.

        This can either ban a Member, in which they must be in the guild. Or this can ban a User, which does not need
        to be in the guild.

        Example for banning a member:

        .. code:: python
            member = guild.get_member(66237334693085184)
            await guild.ban(member)

        Example for banning a user:

        .. code:: python
            user = await client.get_user(66237334693085184)
            await guild.ban(user)

        :param victim: The person to ban.
        :param delete_message_days: The number of days to delete messages.
        """
        if not self.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        if isinstance(victim, dt_member.Member):
            if self.owner == victim:
                raise HierachyError("Cannot ban the owner")

            if victim.guild != self:
                raise ValueError("Member must be from this guild (try `member.user` instead)")

            if victim.top_role >= self.me.top_role:
                raise HierachyError("Top role is equal to or lower than victim's top role")

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
            user = await client.get_user(66237334693085184)
            await guild.unban(user)

        :param user: The user to forgive and unban.
        """
        if not self.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        forgiven_id = user.id

        await self._bot.http.unban_user(self.id, forgiven_id)

    async def add_roles(self, member: 'dt_member.Member', *roles: typing.List['role.Role']):
        """
        Adds roles to a member.

        This will wait until the gateway returns the GUILD_MEMBER_UPDATE with the new role list for the member before
        returning.

        .. code:: python
            roles = filter(lambda r: "Mod" in r.name, guild.roles)
            await guild.add_roles(member, *roles)

        :param member: The member to add roles to.
        :param roles: The roles to add roles to.
        """
        if not self.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        # Ensure we can add all of these roles.
        for _r in roles:
            if _r.position >= self.me.top_role.position:
                raise HierachyError(
                    "Cannot add role {} - it has a higher or equal position to our top role".format(_r.name)
                )

        async def _listener(before, after: dt_member.Member):
            if after.id != member.id:
                return False

            if not all(role in after.roles for role in roles):
                return False

            return True

        role_ids = set([_r.id for _r in member.roles] + [_r.id for _r in roles])
        listener = await curio.spawn(self._bot.wait_for("member_update", _listener))

        await self._bot.http.add_roles(self.id, member.id, role_ids)
        # Now wait for the event to happen on the gateway.
        await listener.join()

        return member
