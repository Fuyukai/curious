"""
Wrappers for Role objects.

.. currentmodule:: curious.dataclasses.role
"""

import functools

from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import member as dt_member
from curious.dataclasses import permissions as dt_permissions


@functools.total_ordering
class Role(Dataclass):
    """
    Represents a role on a server.

    :ivar id: The ID of this role.
    """
    __slots__ = "name", "colour", "hoisted", "mentionable", "permissions", "managed", "position", "guild"

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.get("id"), client)

        #: The name of this role.
        self.name = kwargs.get("name", None)

        #: The colour of this role.
        self.colour = kwargs.get("color", 0)

        #: Is this role hoisted?
        self.hoisted = kwargs.get("hoist", False)

        #: Is this role mentionable?
        self.mentionable = kwargs.get("mentionable", False)

        #: The permissions of this role.
        self.permissions = dt_permissions.Permissions(kwargs.get("permissions", 0))

        #: Is this role managed?
        self.managed = kwargs.get("managed", False)

        #: The position of this role.
        self.position = kwargs.get("position", 0)

        #: The :class:`~.Guild` this role is associated with.
        self.guild = None  # type: dt_guild.Guild

    def __lt__(self, other: 'Role'):
        if not isinstance(other, Role):
            return NotImplemented

        if other.guild != self.guild:
            raise ValueError("Cannot compare roles between guilds")

        return self.position < other.position if self.position != other.position else self.id < other.id

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

    @property
    def mention(self):
        return "<@&{}>".format(self.id)

    def assign_to(self, member: 'dt_member.Member'):
        """
        Assigns this role to a member.

        :param member: The :class:`~.Member` to assign to.
        """
        return self.guild.add_roles(member, self)

    def remove_from(self, member: 'dt_member.Member'):
        return self.guild.remove_roles(member, self)

    def delete(self):
        return self.guild.delete_role(self)

    def edit(self, **kwargs):
        return self.guild.edit_role(self, **kwargs)
