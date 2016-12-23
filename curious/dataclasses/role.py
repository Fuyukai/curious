from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild


class Role(Dataclass):
    """
    Represents a role on a server.
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
        #: TODO: Make this use a Permissions object.
        self.permissions = kwargs.pop("permissions", 0)

        #: Is this role managed?
        self.managed = kwargs.pop("managed", False)

        #: The position of this role.
        self.position = kwargs.pop("position", 0)

        #: The guild this role is associated with.
        self.guild = None  # type: guild.Guild

    @property
    def is_default_role(self):
        """
        :return: If this role is the default role of the guild.
        """
        return self.guild.id == self.id
