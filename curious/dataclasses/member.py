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

    :ivar id: The ID of this member.
    """

    __slots__ = ("_role_ids", "joined_at", "nickname", "guild_id", "presence", "voice",)

    def __init__(self, client, **kwargs):
        super().__init__(kwargs["user"]["id"], client)

        # make the user to use and cache
        self._bot.state.make_user(kwargs["user"])

        #: An iterable of role IDs this member has.
        self._role_ids = [int(rid) for rid in kwargs.get("roles", [])]

        #: The date the user joined the guild.
        self.joined_at = to_datetime(kwargs.get("joined_at", None))

        #: The member's current nickname.
        self.nickname = kwargs.get("nick", None)

        #: The ID of the guild that this member is in.
        self.guild_id = None  # type: int

        #: The current :class:`~.Presence` of this member.
        self.presence = Presence(status=kwargs.get("status", Status.OFFLINE),
                                 game=kwargs.get("game", None))

        #: The current :class:`~.VoiceState` of this member.
        self.voice = None  # type: dt_vs.VoiceState

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`~.Guild` associated with this member. 
        """
        return self._bot.guilds.get(self.guild_id)

    def __hash__(self):
        return hash(self.guild_id) + hash(self.user.id)

    def __eq__(self, other):
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
        new_object._role_ids = self._role_ids.copy()
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
        :return: The underlying user for this member.
        """
        return self._bot.state._users[self.id]

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

        return [self.guild.roles[i] for i in self._role_ids]

    @property
    def colour(self) -> int:
        """
        :return: The computed colour of this user.
        :rtype: int
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
        return next(iter(sorted(self.roles, reverse=True)), self.guild.default_role)

    @property
    def guild_permissions(self):
        """
        :return: The calculated guild permissions for a member.
        :rtype: :class:`.Permissions`
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
    def send(self, content: str, *args, **kwargs):
        return self.user.send(content, *args, **kwargs)

    def ban(self, delete_message_days: int=7):
        """
        Bans this member from the guild.

        :param delete_message_days: The number of days of messages to delete.
        """
        return self.guild.ban(self, delete_message_days=delete_message_days)

    def kick(self):
        """
        Kicks this member from the guild.
        """
        return self.guild.kick(self)

    def add_roles(self, *roles: 'typing.Iterable[dt_role.Role]'):
        """
        Adds roles to this member.

        For more documentation, see :meth:`~.Guild.add_roles`.

        :param roles: The list of roles to add.
        """
        return self.guild.add_roles(self, *roles)

    def remove_roles(self, *roles: 'typing.Iterable[dt_role.Role]'):
        """
        Removes roles from this member.

        For more documentation, see :meth:`~.Guild.remove_roles`.

        :param roles: The list of roles to remove.
        """
        return self.guild.remove_roles(self, *roles)

    def change_nickname(self, new_nickname: typing.Union[str, None]):
        """
        Changes the nickname of this member.

        :param new_nickname: The nickname to change to, None to remove the nickname.
        """
        return self.guild.change_nickname(self, new_nickname)
