"""
Wrappers for Role objects.

.. currentmodule:: curious.dataclasses.role
"""

import functools
import typing

from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import member as dt_member
from curious.dataclasses import permissions as dt_permissions


class _MentionableRole(object):
    """
    A wrapper class that makes a role mentionable for a short time period.
    
    .. code-block:: python
    
        async with role.allow_mentions():
            await ctx.channel.send(role.mention)
            
    """
    def __init__(self, r: 'Role'):
        self.role = r

    def allow_mentions(self):
        return self.role.edit(mentionable=True)

    def disallow_mentions(self):
        return self.role.edit(mentionable=False)

    def __aenter__(self):
        return self.allow_mentions()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disallow_mentions()
        return False


@functools.total_ordering
class Role(Dataclass):
    """
    Represents a role on a server.
    """
    __slots__ = "name", "colour", "hoisted", "mentionable", "permissions", "managed", "position", \
                "guild_id"

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

        #: The ID of the guild associated with this Role.
        self.guild_id = int(kwargs.get("guild_id", 0))  # type: dt_guild.Guild

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
        obb.guild_id = self.guild_id

        return obb

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`.Guild` associated with this role. 
        """
        return self._bot.guilds[self.guild_id]

    @property
    def is_default_role(self) -> bool:
        """
        :return: If this role is the default role of the guild.
        """
        return self.guild.id == self.id

    @property
    def mention(self) -> str:
        """
        Gets the string that can be used to mention this role. 
        
        .. warning::
        
            If :attr:`.Role.mentionable` is ``False``, this will not actually mention the role.
        
        """
        return "<@&{}>".format(self.id)

    def assign_to(self, member: 'dt_member.Member') -> 'typing.Awaitable[dt_member.Member]':
        """
        Assigns this role to a member.
        
        .. seealso::
        
            :meth:`.Guild.add_roles`

        :param member: The :class:`~.Member` to assign to.
        """
        return self.guild.add_roles(member, self)

    def remove_from(self, member: 'dt_member.Member'):
        """
        Removes this role from a member.
        
        .. seealso::
        
            :meth:`.Guild.remove_roles`
        
        :param member: The :class:`~.Member` to assign to. 
        """
        return self.guild.remove_roles(member, self)

    def delete(self):
        """
        Deletes this role in its guild.
        
        .. seealso::
            
            :meth:`.Guild.delete_role`
        """
        return self.guild.delete_role(self)

    def edit(self, **kwargs):
        """
        Edits this role in its guild.
        
        .. seealso::
        
            :meth:`.Guild.edit_role`
        """
        return self.guild.edit_role(self, **kwargs)
