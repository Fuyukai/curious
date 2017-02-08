import copy
import typing

from curious.dataclasses.bases import Dataclass
from curious.dataclasses.permissions import Permissions
from curious.dataclasses.role import Role
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

    __slots__ = ("user", "_roles", "joined_at", "nickname", "guild", "game", "_status", "voice",)

    def __init__(self, client, **kwargs):
        super().__init__(kwargs["user"]["id"], client)

        #: The :class:`User` object associated with this member.
        self.user = client.state.make_user(kwargs.get("user"))

        #: A dictionary of :class:`Role` this user has.
        self._roles = {}

        #: The date the user joined the guild.
        self.joined_at = to_datetime(kwargs.pop("joined_at", None))

        #: The member's current nickname.
        self.nickname = kwargs.pop("nick", None)

        #: The member's current :class:`Guild`.
        self.guild = None  # type: guild.Guild

        #: The current :class:`Game` this Member is playing.
        self.game = None  # type: Game

        #: The current :class:`Status` of this member.
        self._status = None  # type: Status

        #: The current :class:`VoiceState` of this member.
        self.voice = None  # type: dt_vs.VoiceState

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

        new_object.user = self.user._copy()

        return new_object

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
        :rtype: Status
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
    def roles(self) -> typing.Iterable[Role]:
        """
        :return: A list of roles this user has.
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
    def top_role(self) -> Role:
        """
        :return: This member's top-most :class:`Role`.
        """
        return next(iter(sorted(self.roles, reverse=True)), self.guild.default_role)

    @property
    def guild_permissions(self):
        """
        :return: The calculated guild permissions for a member.
        :rtype: Permissions
        """
        if self == self.guild.owner:
            return Permissions.all()

        bitfield = 0
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

    def add_roles(self, *roles: typing.Iterable[Role]):
        """
        Adds roles to this member.

        For more documentation, see :meth:`Guild.add_roles`.

        :param roles: The list of roles to add.
        """
        return self.guild.add_roles(self, *roles)

    def remove_roles(self, *roles: typing.Iterable[Role]):
        """
        Removes roles from this member.

        For more documentation, see :meth:`Guild.remove_roles`.

        :param roles: The list of roles to remove.
        """
        return self.guild.remove_roles(self, *roles)

    def change_nickname(self, new_nickname: typing.Union[str, None]):
        """
        Changes the nickname of this member.

        :param new_nickname: The nickname to change to, None to remove the nickname.
        """
        return self.guild.change_nickname(self, new_nickname)
