import copy
import typing

from curious.dataclasses.bases import Dataclass, Messagable
from curious.dataclasses.permissions import Permissions
from curious.dataclasses.role import Role
from curious.dataclasses.status import Game, Status
from curious.dataclasses import user as dt_user
from curious.dataclasses import guild
from curious.util import to_datetime


class Member(Dataclass, Messagable):
    """
    A member is a user attached to a guild.

    :ivar id: The ID of this member.
    :ivar user: The :class:`curious.dataclasses.user.User` object that this member is associated with.
    :ivar joined_at: The :class:`datetime.datetime` that represents when this member joined the server.
    :ivar guild: The :class:`curious.dataclasses.guild.Guild` object that this member is associated with.
    :ivar nickname: The nickname this member has in the guild.
    :ivar game: The :class:`curious.dataclasses.status.Game` object that this member is playing. None for no game.
    :ivar status: The current status of this member.
    """
    def __init__(self, client, **kwargs):
        super().__init__(kwargs["user"]["id"], client)

        #: The user object associated with this member.
        self.user = dt_user.User(client, **kwargs.get("user"))

        #: A dictionary of roles this user has.
        self._roles = {}

        #: The date the user joined the guild.
        self.joined_at = to_datetime(kwargs.pop("joined_at", None))

        #: The member's current nickname.
        self.nickname = kwargs.pop("nick", None)

        #: The member's current guild.
        self.guild = None  # type: guild.Guild

        #: The current game this Member is playing.
        self.game = None  # type: Game

        #: The current status of this member.
        self._status = None  # type: Status

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
    def name(self):
        """
        :return: The computed display name of this user.
        """
        return self.nickname if self.nickname else self.user.username

    @property
    def status(self) -> Status:
        return self._status

    @status.setter
    def status(self, value):
        self._status = Status(value)

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
        """
        roles = sorted(self.roles, key=lambda r: r.position, reverse=True)
        roles = filter(lambda role: role.colour, roles)
        try:
            return next(roles).colour
        except StopIteration:
            return 0

    @property
    def top_role(self) -> Role:
        """
        :return: This member's top-most role.
        """
        return next(sorted(self.roles, key=lambda r: r.position, reverse=True))

    @property
    def guild_permissions(self):
        """
        :return: The calculated guild permissions for a member.
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
