"""
Wrappers for Member objects (Users with guilds).

.. currentmodule:: curious.dataclasses.member
"""

import typing

from curious.dataclasses import guild as dt_guild, role as dt_role, user as dt_user, \
    voice_state as dt_vs
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.permissions import Permissions
from curious.dataclasses.presence import Game, Presence, Status
from curious.util import to_datetime


class Member(Dataclass):
    """
    A member represents somebody who is inside a guild.
    """

    __slots__ = ("_user_data", "role_ids", "joined_at", "nickname", "guild_id", "presence")

    def __init__(self, client, **kwargs):
        super().__init__(kwargs["user"]["id"], client)

        # copy user data for when the user is decached
        self._user_data = kwargs["user"]
        self._bot.state.make_user(self._user_data)

        #: An iterable of role IDs this member has.
        self.role_ids = [int(rid) for rid in kwargs.get("roles", [])]

        #: The date the user joined the guild.
        self.joined_at = to_datetime(kwargs.get("joined_at", None))

        #: The member's current nickname.
        self.nickname = kwargs.get("nick", None)

        #: The ID of the guild that this member is in.
        self.guild_id = None  # type: int

        #: The current :class:`~.Presence` of this member.
        self.presence = Presence(status=kwargs.get("status", Status.OFFLINE),
                                 game=kwargs.get("game", None))

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`~.Guild` associated with this member. 
        """
        return self._bot.guilds.get(self.guild_id)

    @property
    def voice(self) -> 'dt_vs.VoiceState':
        """
        :return: The :class:`~.VoiceState` associated with this member.
        """
        try:
            return self.guild._voice_states[self.id]
        except (AttributeError, KeyError):
            return None

    def __hash__(self) -> int:
        return hash(self.guild_id) + hash(self.user.id)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Member):
            return NotImplemented

        return other.guild == self.guild and other.user == self.user

    def _copy(self):
        """
        Copies a member object.
        """
        new_object = object.__new__(self.__class__)  # type: Member
        new_object._bot = self._bot

        new_object.id = self.id
        new_object.role_ids = self.role_ids.copy()
        new_object.joined_at = self.joined_at
        new_object.guild_id = self.guild_id
        new_object.presence = self.presence
        new_object.nickname = self.nickname

        return new_object

    def __del__(self):
        try:
            self._bot.state._check_decache_user(self.id)
        except AttributeError:
            # during shutdown
            pass

    @property
    def user(self) -> 'dt_user.User':
        """
        :return: The underlying :class:`.User` for this member.
        """
        try:
            return self._bot.state._users[self.id]
        except KeyError:
            # don't go through make_user as it'll cache it
            return dt_user.User(self._bot, **self._user_data)

    @property
    def name(self) -> str:
        """
        :return: The computed display name of this user.
        """
        return self.nickname if self.nickname else self.user.username

    @property
    def mention(self) -> str:
        """
        :return: A string that mentions this member. 
        """
        if self.nickname:
            return "<@!{}>".format(self.id)

        return self.user.mention

    @property
    def status(self) -> Status:
        """
        :return: The current :class:`~.Status` of this member.
        """
        return self.presence.status if self.presence else Status.OFFLINE

    @property
    def game(self) -> Game:
        """
        :return: The current :class:`~.Game` this member is playing.
        """
        if not self.presence:
            return None

        if self.presence.status == Status.OFFLINE:
            return None

        return self.presence.game

    @property
    def roles(self) -> 'typing.Iterable[dt_role.Role]':
        """
        :return: A list of :class:`~.Role` that this member has. 
        """
        if not self.guild:
            return None

        roles = []
        for id in self.role_ids:
            try:
                roles.append(self.guild.roles[id])
            except (KeyError, AttributeError):
                pass

        return sorted(roles)

    @property
    def colour(self) -> int:
        """
        :return: The computed colour of this user.
        """
        roles = sorted(self.roles, reverse=True)
        # NB: you can abuse discord and edit the defualt role's colour
        # so explicitly check that it isn't the default role, and make sure it has a colour
        # in order to get the correct calculated colour
        roles = filter(lambda role: not role.is_default_role and role.colour, roles)
        try:
            return next(roles).colour
        except StopIteration:
            return 0

    @property
    def top_role(self) -> 'dt_role.Role':
        """
        :return: This member's top-most :class:`~.Role`.
        """
        try:
            return next(iter(sorted(self.roles, reverse=True)), self.guild.default_role)
        except AttributeError:
            return None

    @property
    def guild_permissions(self) -> Permissions:
        """
        :return: The calculated guild permissions for a member.
        """
        if self == self.guild.owner:
            return Permissions.all()

        bitfield = 0
        # add the default roles
        bitfield |= self.guild.default_role.permissions.bitfield
        for role in self.roles:
            bitfield |= role.permissions.bitfield

        permissions = Permissions(bitfield)
        if permissions.administrator:
            return Permissions.all()

        return permissions

    # Member methods.
    async def send(self, content: str, *args, **kwargs):
        """
        Sends a message to a member in DM.

        This is a shortcut for :meth:`.User.send`.
        """
        return await self.user.send(content, *args, **kwargs)

    async def ban(self, delete_message_days: int = 7):
        """
        Bans this member from the guild.

        :param delete_message_days: The number of days of messages to delete.
        """
        return await self.guild.ban(self, delete_message_days=delete_message_days)

    async def kick(self):
        """
        Kicks this member from the guild.
        """
        return await self.guild.kick(self)

    async def add_roles(self, *roles: 'typing.Iterable[dt_role.Role]'):
        """
        Adds roles to this member.

        For more documentation, see :meth:`~.Guild.add_roles`.

        :param roles: The list of roles to add.
        """
        return await self.guild.add_roles(self, *roles)

    async def remove_roles(self, *roles: 'typing.Iterable[dt_role.Role]'):
        """
        Removes roles from this member.

        For more documentation, see :meth:`~.Guild.remove_roles`.

        :param roles: The list of roles to remove.
        """
        return await self.guild.remove_roles(self, *roles)

    async def change_nickname(self, new_nickname: typing.Union[str, None]):
        """
        Changes the nickname of this member.

        :param new_nickname: The nickname to change to, None to remove the nickname.
        """
        return await self.guild.change_nickname(self, new_nickname)
