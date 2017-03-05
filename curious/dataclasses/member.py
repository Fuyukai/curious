"""
Wrappers for Member objects (Users with guilds).

.. currentmodule:: curious.dataclasses.member
"""

import copy
import typing

from curious.dataclasses.bases import Dataclass
from curious.dataclasses.permissions import Permissions
from curious.dataclasses import role as dt_role
from curious.dataclasses.status import Game, Status
from curious.dataclasses import voice_state as dt_vs
from curious.dataclasses import user as dt_user
from curious.dataclasses import guild
from curious.util import to_datetime


class Member(Dataclass):
    """
    A member represents somebody who is inside a guild.

    :ivar id: The ID of this member.
    """

    __slots__ = ("_roles", "joined_at", "nickname", "guild", "game", "_status", "voice",)

    def __init__(self, client, **kwargs):
        super().__init__(kwargs["user"]["id"], client)

        # make the user to use and cache
        self._bot.state.make_user(kwargs["user"])

        #: A dictionary of :class:`Role` this user has.
        self._roles = {}

        #: The date the user joined the guild.
        self.joined_at = to_datetime(kwargs.get("joined_at", None))

        #: The member's current nickname.
        self.nickname = kwargs.get("nick", None)

        #: The member's current :class:`~.Guild`.
        self.guild = None  # type: guild.Guild

        #: The current :class:`~.Game` this Member is playing.
        self.game = None  # type: Game

        #: The current :class:`~.Status` of this member.
        self._status = None  # type: Status

        #: The current :class:`~.VoiceState` of this member.
        self.voice = None  # type: dt_vs.VoiceState

    def __hash__(self):
        return hash(self.guild.id) + hash(self.user.id)

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
        new_object._roles = self._roles.copy()
        new_object.joined_at = self.joined_at
        new_object.guild = self.guild
        new_object.game = copy.deepcopy(self.game)
        new_object._status = self._status
        new_object.nickname = self.nickname

        return new_object

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
    def mention(self):
        if self.nickname:
            return "<@!{}>".format(self.id)

        return self.user.mention

    @property
    def status(self) -> Status:
        """
        :return: The current status of this member.
        :rtype: :class:`~.Status`
        """
        return self._status

    @status.setter
    def status(self, value):
        if value is None:
            return

        if not isinstance(value, Status):
            value = Status(value)
        self._status = value

    @property
    def roles(self) -> 'typing.Iterable[dt_role.Role]':
        """
        :return: A list of :class:`~.Role` this user has.
        """
        return self._roles.values()

    @property
    def colour(self) -> int:
        """
        :return: The computed colour of this user.
        :rtype: int
        """
        roles = sorted(self.roles, reverse=True)
        roles = filter(lambda role: role.colour, roles)
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
