# This file is part of curious.
#
# curious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# curious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with curious.  If not, see <http://www.gnu.org/licenses/>.

"""
Wrappers for Role objects.

.. currentmodule:: curious.dataclasses.role
"""
from __future__ import annotations

import copy
import functools
from typing import TYPE_CHECKING, Union

from curious.dataclasses.bases import Dataclass
from curious.dataclasses.permissions import Permissions
from curious.exc import PermissionsError

if TYPE_CHECKING:
    from curious.dataclasses.guild import Guild
    from curious.dataclasses.member import Member


class _MentionableRole(object):
    """
    A wrapper class that makes a role mentionable for a short time period.

    .. code-block:: python3

        async with role.allow_mentions():
            await ctx.channel.messages.send(role.mention)

    """

    def __init__(self, r: Role):
        self.role = r

    async def allow_mentions(self):  # noqa
        return await self.role.edit(mentionable=True)

    async def disallow_mentions(self):  # noqa
        return await self.role.edit(mentionable=False)

    def __aenter__(self):  # noqa
        return self.allow_mentions()

    async def __aexit__(self, exc_type, exc_val, exc_tb):  # noqa
        await self.disallow_mentions()
        return False


@functools.total_ordering
class Role(Dataclass):
    """
    Represents a role on a server.
    """

    __slots__ = (
        "name",
        "colour",
        "hoisted",
        "mentionable",
        "permissions",
        "managed",
        "position",
        "guild_id",
    )

    def __init__(self, client, **kwargs) -> None:
        super().__init__(kwargs.get("id"), client)

        #: The name of this role.
        self.name: str = kwargs["name"]

        #: The colour of this role.
        self.colour: int = kwargs.get("color", 0)

        #: Is this role hoisted?
        self.hoisted: bool = kwargs.get("hoist", False)

        #: Is this role mentionable?
        self.mentionable: bool = kwargs.get("mentionable", False)

        #: The permissions of this role.
        self.permissions = Permissions(int(kwargs.get("permissions", 0)))

        #: Is this role managed?
        self.managed: bool = kwargs.get("managed", False)

        #: The position of this role.
        self.position: int = kwargs.get("position", 0)

        #: The ID of the guild associated with this Role.
        self.guild_id: int = None  # noqa

    def __lt__(self, other: Role) -> bool:
        if not isinstance(other, Role):
            return NotImplemented

        if other.guild != self.guild:
            raise ValueError("Cannot compare roles between guilds")

        return (
            self.position < other.position
            if self.position != other.position
            else self.id < other.id
        )

    def _copy(self) -> "Role":
        return copy.copy(self)

    @property
    def guild(self) -> Guild:
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

    def allow_mentions(self) -> _MentionableRole:
        """
        Temporarily allows this role to be mentioned during.

        .. code-block:: python3

            async with role.allow_mentions():
                await ctx.channel.messages.send(role.mention)
        """
        return _MentionableRole(self)

    @property
    def mention(self) -> str:
        """
        Gets the string that can be used to mention this role.

        .. warning::

            If :attr:`.Role.mentionable` is ``False``, this will not actually mention the role.

        """
        return f"<@&{self.id}>"

    async def assign_to(self, member: Member) -> Role:
        """
        Assigns this role to a member.

        .. seealso::

            :meth:`.MemberRoleContainer.add`

        :param member: The :class:`.Member` to assign to.
        """
        await member.roles.add(self)
        return self

    async def remove_from(self, member: Member):
        """
        Removes this role from a member.

        .. seealso::

            :meth:`.MemberRoleContainer.remove`

        :param member: The :class:`.Member` to assign to.
        """
        await member.roles.remove(self)
        return self

    async def delete(self) -> Role:
        """
        Deletes this role.
        """
        if not self.guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        await self._bot.http.delete_role(self.guild.id, self.id)
        return self

    async def edit(
        self,
        *,
        name: str = None,
        permissions: Union[int, Permissions] = None,
        colour: int = None,
        position: int = None,
        hoist: bool = None,
        mentionable: bool = None,
    ) -> "Role":
        """
        Edits this role.

        :param name: The name of the role.
        :param permissions: The permissions that the role has.
        :param colour: The colour of the role.
        :param position: The position in the sorting list that the role has.
        :param hoist: Is this role hoisted (shows separately in the role list)?
        :param mentionable: Is this mentionable by everyone?
        """
        if not self.guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        if permissions is not None:
            if isinstance(permissions, Permissions):
                permissions = permissions.bitfield

        async with self._bot.events.wait_for_manager("role_update", lambda b, a: a.id == self.id):
            await self._bot.http.edit_role(
                self.guild_id,
                self.id,
                name=name,
                permissions=permissions,
                colour=colour,
                hoist=hoist,
                position=position,
                mentionable=mentionable,
            )
        return self
