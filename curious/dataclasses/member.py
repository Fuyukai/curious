import copy
import typing

from curious.dataclasses.bases import Dataclass
from curious.dataclasses.role import Role
from curious.dataclasses.status import Game, Status
from curious.dataclasses.user import User
from curious.dataclasses import guild


class Member(Dataclass):
    """
    A member is a user attached to a guild.
    """
    def __init__(self, client, **kwargs):
        super().__init__(kwargs["user"]["id"], client)

        #: The user object associated with this member.
        self.user = User(client, **kwargs.get("user"))

        #: A dictionary of roles this user has.
        self._roles = {}

        #: The date the user joined the guild.
        # TODO: Make this a datetime.
        self.joined_at = kwargs.pop("joined_at", None)

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
