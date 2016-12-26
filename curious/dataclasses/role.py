from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild
from curious.dataclasses.permissions import Permissions


class Role(Dataclass):
    """
    Represents a role on a server.

    :ivar name: The name of this role.
    :ivar colour: The integer colour of this role.
    :ivar hoisted: Is this role hoisted?
    :ivar mentionable: Is this role mentionable?
    :ivar permissions: A :class:`curious.dataclasses.permissions.Permissions` object that represents the permissions
    this role has.
    :ivar managed: Is this role managed by an integration?
    :ivar position: The raw position in the role list.
    :ivar guild: The :class:`curious.dataclasses.guild.Guild` object this role belongs to.
    """

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.pop("id"), client)

        #: The name of this role.
        self.name = kwargs.pop("name", None)

        #: The colour of this role.
        self.colour = kwargs.pop("color", 0)

        #: Is this role hoisted?
        self.hoisted = kwargs.pop("hoist", False)

        #: Is this role mentionable?
        self.mentionable = kwargs.pop("mentionable", False)

        #: The permissions of this role.
        self.permissions = Permissions(kwargs.pop("permissions", 0))

        #: Is this role managed?
        self.managed = kwargs.pop("managed", False)

        #: The position of this role.
        self.position = kwargs.pop("position", 0)

        #: The guild this role is associated with.
        self.guild = None  # type: guild.Guild

    def _copy(self):
        obb = object.__new__(self.__class__)

        obb.name = self.name
        obb.colour = self.colour
        obb.hoisted = self.hoisted
        obb.permissions = self.permissions
        obb.managed = self.managed
        obb.position = self.position
        obb.guild = self.guild

        return obb

    @property
    def is_default_role(self):
        """
        :return: If this role is the default role of the guild.
        """
        return self.guild.id == self.id
