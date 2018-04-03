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
Wrappers for Member objects (Users with guilds).

.. currentmodule:: curious.dataclasses.member
"""
import datetime
from typing import List

import collections

from curious.dataclasses import guild as dt_guild, role as dt_role, user as dt_user, \
    voice_state as dt_vs
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.permissions import Permissions
from curious.dataclasses.presence import Game, Presence, Status
from curious.exc import HierarchyError, PermissionsError
from curious.util import to_datetime


class Nickname(object):
    """
    Represents the nickname of a :class:`.Member`.
    """
    def __init__(self, parent: 'Member', value: str):
        self.parent = parent
        self.value = value

    def __eq__(self, other):
        if other is None and self.value in [None, ""]:
            return True

        if isinstance(other, Nickname):
            return self.value == other.value

        return self.value == other

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self) -> str:
        if self.value is not None:
            return self.value

        return ""

    def __repr__(self) -> str:
        return f"<Nickname value={self.value}>"

    async def set(self, new_nickname: str) -> 'Nickname':
        """
        Sets the nickname of the username.

        :param new_nickname: The new nickname of this user. If None, will reset the nickname.
        """

        # Ensure we don't try and set a bad nickname, which makes an empty listener.
        if new_nickname == self:
            return self

        guild: dt_guild.Guild = self.parent.guild

        me = False
        if self.parent == self.parent.guild.me:
            me = True
            if not guild.me.guild_permissions.change_nickname:
                raise PermissionsError("change_nickname")
        else:
            if not guild.me.guild_permissions.manage_nicknames:
                raise PermissionsError("manage_nicknames")

        if self.parent.top_role >= guild.me.top_role and self.parent != guild.me:
            raise HierarchyError("Top role is equal to or lower than victim's top role")

        if new_nickname is not None and len(new_nickname) > 32:
            raise ValueError("Nicknames cannot be longer than 32 characters")

        async def _listener(before, after):
            return after.guild == guild and after.id == self.parent.id

        async with self.parent._bot.events.wait_for_manager("guild_member_update", _listener):
            await self.parent._bot.http.change_nickname(guild.id, new_nickname,
                                                        member_id=self.parent.id, me=me)

        # the wait_for means at this point the nickname has been changed
        return self.parent.nickname

    async def reset(self) -> 'Nickname':
        """
        Resets a member's nickname.
        """
        return await self.set(None)


class MemberRoleContainer(collections.Sequence):
    """
    Represents the roles of a :class:`.Member`.
    """

    def __init__(self, member: 'Member'):
        self._member = member

    def _sorted_roles(self) -> 'List[dt_role.Role]':
        if not self._member.guild:
            return []

        roles = filter(
            lambda r: r is not None,
            map(self._member.guild.roles.get, self._member.role_ids)
        )

        return sorted(roles, reverse=True)

    # opt: the default Sequence makes us re-create the sorted role list constantly
    # we don't wanna cache it, without introducing invalidation hell
    # so we just put `__iter__` on `_sorted_roles`
    def __iter__(self) -> type(iter([])):
        return iter(self._sorted_roles())

    def __len__(self) -> int:
        return len(self._member.role_ids)

    def __getitem__(self, item: int):
        return self._sorted_roles()[item]

    @property
    def top_role(self) -> 'dt_role.Role':
        """
        :return: The top :class:`.Role` for this member.
        """
        roles = self._sorted_roles()
        if len(roles) <= 0:
            return self._member.guild.default_role

        return self[0]

    async def add(self, *roles: 'dt_role.Role'):
        """
        Adds roles to this member.

        :param roles: The :class:`.Role` objects to add to this member's role list.
        """

        if not self._member.guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        # Ensure we can add all of these roles.
        for _r in roles:
            if _r >= self._member.guild.me.top_role:
                msg = "Cannot add role {} - it has a higher or equal position to our top role" \
                    .format(_r.name)
                raise HierarchyError(msg)

        async def _listener(before, after: Member):
            if after.id != self._member.id:
                return False

            if not all(role in after.roles for role in roles):
                return False

            return True

        async with self._member._bot.events.wait_for_manager("guild_member_update", _listener):
            role_ids = set([_r.id for _r in self._member.roles] + [_r.id for _r in roles])
            await self._member._bot.http.edit_member_roles(
                self._member.guild_id, self._member.id, role_ids
            )

    async def remove(self, *roles: 'dt_role.Role'):
        """
        Removes roles from this member.

        :param roles: The roles to remove.
        """
        if not self._member.guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        for _r in roles:
            if _r >= self._member.guild.me.top_role:
                msg = "Cannot remove role {} - it has a higher or equal position to our top role" \
                    .format(_r.name)
                raise HierarchyError(msg)

        async def _listener(before, after: Member):
            if after.id != self._member.id:
                return False

            if not all(role not in after.roles for role in roles):
                return False

            return True

        # Calculate the roles to keep.
        to_keep = set(self._member.roles) - set(roles)

        async with self._member._bot.events.wait_for_manager("guild_member_update", _listener):
            role_ids = set([_r.id for _r in to_keep])
            await self._member._bot.http.edit_member_roles(self._member.guild_id, self._member.id,
                                                           role_ids)


class Member(Dataclass):
    """
    A member represents somebody who is inside a guild.
    """

    __slots__ = ("_user_data", "role_ids", "joined_at", "_nickname", "guild_id", "presence",
                 "roles")

    def __init__(self, client, **kwargs):
        super().__init__(kwargs["user"]["id"], client)

        # copy user data for when the user is decached
        self._user_data = kwargs["user"]
        self._bot.state.make_user(self._user_data)

        #: An iterable of role IDs this member has.
        self.role_ids = [int(rid) for rid in kwargs.get("roles", [])]

        #: A :class:`._MemberRoleContainer` that represents the roles of this member.
        self.roles = MemberRoleContainer(self)

        #: The date the user joined the guild.
        self.joined_at = to_datetime(kwargs.get("joined_at", None))  # type: datetime.datetime

        nick = kwargs.get("nick")
        #: The member's current :class:`.Nickname`.
        self._nickname = Nickname(self, nick)  # type: Nickname

        #: The ID of the guild that this member is in.
        self.guild_id = None  # type: int

        #: The current :class:`.Presence` of this member.
        self.presence = Presence(status=kwargs.get("status", Status.OFFLINE),
                                 game=kwargs.get("game", None))

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`.Guild` associated with this member.
        """
        return self._bot.guilds.get(self.guild_id)

    @property
    def voice(self) -> 'dt_vs.VoiceState':
        """
        :return: The :class:`.VoiceState` associated with this member.
        """
        try:
            return self.guild._voice_states[self.id]
        except (AttributeError, KeyError):
            return None

    @property
    def nickname(self) -> Nickname:
        """
        Represents a member's nickname.

        :getter: A :class:`._Nickname` for this member.
        :setter: Coerces a string nickname into a :class:`._Nickname`. Do not use.
        """
        return self._nickname

    @nickname.setter
    def nickname(self, value: str):
        if isinstance(value, Nickname):
            # unwrap nicknames, in case of error
            value = value.value
        self._nickname.value = value

    def __hash__(self) -> int:
        return hash(self.guild_id) + hash(self.user.id)

    def __eq__(self, other) -> bool:
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
        new_object.role_ids = self.role_ids.copy()
        new_object.joined_at = self.joined_at
        new_object.guild_id = self.guild_id
        new_object.presence = self.presence
        new_object._nickname = self._nickname

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
        :return: The underlying :class:`.User` for this member.
        """
        try:
            return self._bot.state._users[self.id]
        except KeyError:
            # don't go through make_user as it'll cache it
            return dt_user.User(self._bot, **self._user_data)

    @property
    def name(self) -> str:
        """
        :return: The computed display name of this user.
        """
        return self.nickname if self.nickname != None else self.user.username

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
        :return: The current :class:`.Status` of this member.
        """
        return self.presence.status if self.presence else Status.OFFLINE

    @property
    def game(self) -> Game:
        """
        :return: The current :class:`.Game` this member is playing.
        """
        if not self.presence:
            return None

        if self.presence.status == Status.OFFLINE:
            return None

        return self.presence.game

    @property
    def colour(self) -> int:
        """
        :return: The computed colour of this user.
        """
        roles = reversed(self.roles)

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
        :return: This member's top-most :class:`.Role`.
        """
        return self.roles.top_role

    @property
    def guild_permissions(self) -> Permissions:
        """
        :return: The calculated guild permissions for a member.
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
    async def send(self, content: str, *args, **kwargs):
        """
        Sends a message to a member in DM.

        This is a shortcut for :meth:`.User.send`.
        """
        return await self.user.send(content, *args, **kwargs)

    async def ban(self, delete_message_days: int = 7):
        """
        Bans this member from the guild.

        :param delete_message_days: The number of days of messages to delete.
        """
        return await self.guild.bans.add(self, delete_message_days=delete_message_days)

    async def kick(self):
        """
        Kicks this member from the guild.
        """
        return await self.guild.kick(self)
