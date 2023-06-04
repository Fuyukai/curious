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
Wrappers for Guild objects.

.. currentmodule:: curious.dataclasses.guild
"""
from __future__ import annotations

import abc
import copy
import datetime
import enum
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil
from os import PathLike
from types import MappingProxyType
from typing import (
    TypeVar,
    Iterator,
    Mapping,
    Any,
    List,
    Union,
    Tuple,
    Dict,
    MutableMapping,
    AsyncGenerator,
    Optional,
    AsyncIterator,
)

import trio

from curious.core.httpclient import Endpoints
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.channel import Channel
from curious.dataclasses.channel_type import ChannelType
from curious.dataclasses.emoji import Emoji
from curious.dataclasses.invite import Invite
from curious.dataclasses.member import Member
from curious.dataclasses.permissions import Overwrite
from curious.dataclasses.presence import Presence, Status
from curious.dataclasses.role import Role
from curious.dataclasses.user import User
from curious.dataclasses.voice_state import VoiceState
from curious.dataclasses.webhook import Webhook
from curious.exc import CuriousError, HTTPException, HierarchyError, PermissionsError
from curious.util import AsyncIteratorWrapper, base64ify

DEFAULT = TypeVar("DEFAULT")


class MFALevel(enum.IntEnum):
    """
    Represents the MFA level of a :class:`.Guild`.
    """

    #: Used when MFA authentication is **disabled**.
    #: This means moderation actions will not require multi-factor auth.
    DISABLED = 0

    #: Used when MFA authentication is **enabled**.
    #: This means moderation actions *will* require multi-factor auth.
    ENABLED = 1


class VerificationLevel(enum.IntEnum):
    """
    Represents the verification levels for a :class:`.Guild`.
    """

    #: No verification level.
    #: All users can speak after joining immediately.
    NONE = 0

    #: Low verification level.
    #: Users must have a verified email on their account.
    LOW = 1

    #: Medium verification level.
    #: Users must have been on Discord for longer than 5 minutes.
    MEDIUM = 2

    #: High/tableflip verification level.
    #: Users must have been on the server for longer than 10 minutes.
    TABLEFLIP = 3

    #: Extreme/double tableflip verification level.
    #: Users must have a phone number associated with their account.
    DOUBLE_TABLEFLIP = 4

    def can_speak(self, member: Member) -> bool:
        """
        Checks if a :class:`.Member` can speak in their :class:`.Guild`.

        :param member: The member to check.
        :return: True if they can speak, False if they can't.
        """
        # none always allows people to speak
        if self is VerificationLevel.NONE:
            return True

        if self is VerificationLevel.LOW:
            # can't validate, assume True
            if member.user.verified is None:
                return True

            return member.user.verified is True

        if self is VerificationLevel.MEDIUM:
            dt = datetime.datetime.now() - datetime.timedelta(minutes=5)

            # ensure their created at time is before 5 minutes before now
            if member.user.created_at < dt:
                return True

        if self is VerificationLevel.TABLEFLIP:
            dt = datetime.datetime.now() - datetime.timedelta(minutes=10)

            # ensure their joined at time is before 10 minutes before now
            if member.joined_at and member.joined_at < dt:
                return True

        # other verification levels ???
        return True


class NotificationLevel(enum.IntEnum):
    """
    Represents the default notification level for a :class:`.Guild`.
    """

    #: All messages notify members, by default.
    ALL_MESSAGES = 0

    #: Only mentions notify members, by default.
    ONLY_MENTIONS = 1


class ContentFilterLevel(enum.IntEnum):
    """
    Represents the content filter level for a :class:`.Guild`.
    """

    #: No messages will be scanned.
    SCAN_NONE = 0

    #: Messages from users without roles will be scanned.
    SCAN_WITHOUT_ROLES = 1

    #: All messages will be scanned.
    SCAN_ALL = 2


class _WrapperBase(Mapping, Iterable):
    """
    Represents the base class for a wrapper object.
    """

    __slots__ = ()

    @property
    @abc.abstractmethod
    def view(self) -> Mapping[int, Dataclass]:
        """
        Represents a read-only view for this wrapper.
        """

    def __iter__(self) -> Iterator[Any]:
        return iter(self.view.keys())

    def __repr__(self) -> str:
        return "<{} items='{}'>".format(type(self).__name__, self.view)


class GuildChannelWrapper(_WrapperBase):
    """
    A wrapper for channels on a guild. This provides some convenience methods which make channel
    management more fluent.
    """

    __slots__ = "_guild", "_channels"

    def __init__(self, guild: Guild):
        """
        :param guild: The :class:`.Guild` object that owns this wrapper.
        """
        self._guild = guild

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, GuildChannelWrapper):
            return False

        return other._guild.id == self._guild.id and other._guild.channels == self._guild.channels

    @property
    def view(self) -> Mapping[int, Channel]:
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._guild._channels)

    def __getitem__(self, key) -> Channel:
        default = object()
        got = self.get(key, default=default)
        if got is default:
            raise KeyError(key)

        return got

    def __len__(self) -> int:
        return len(self._guild._channels)

    # overwritten methods from the abc
    def get(self, key: Union[str, int], default: DEFAULT = None) -> Union[Channel, DEFAULT]:
        """
        Gets a channel by name or ID.

        :param key: The key to use. This can be the ID of the channel, or the name of the channel.
        :param default: The default value to use, if the channel cannot be found.
        :return: A :class:`.Channel`, if it was found.
        """
        if isinstance(key, int):
            return self._guild._channels.get(key, default)
        else:
            return self._get_by_name(key, default=default)

    def _get_by_name(self, name: str, default: DEFAULT = None) -> Union[Channel, DEFAULT]:
        """
        Gets a channel by name.

        .. warning::

            This will return the first channel in the channel list. If you want to get a channel
            in a specific category, use :meth:`.Channel.get_by_name`

        :param name: The name of the channel to get.
        :param default: The default value to get, if the channel cannot be found.
        :return: A :class:`.Channel` if it can be found.
        """
        s = sorted(self._guild._channels.values(), key=lambda c: c.position)
        try:
            return next(filter(lambda ch: ch.name == name, s))
        except StopIteration:
            return default

    async def create(
        self,
        name: str,
        type_: ChannelType = None,
        permission_overwrites: List[Overwrite] = None,
        *,
        parent: Channel = None,
        bitrate: int = 64,
        user_limit: int = 0,
        topic: str = None,
    ) -> Channel:
        """
        Creates a new channel.

        :param name: The name of the channel.
        :param type_: The :class:`.ChannelType` of the channel.
        :param permission_overwrites: The list of permission overwrites to use for this channel.

        For guild channels:

        :param parent: The parent :class:`.Channel` for this channel.

        For voice channels:

        :param bitrate: The bitrate of the channel, if it is a voice channel, in kbit/s.
        :param user_limit: The maximum number of users that can be in the channel.

        For text channels:

        :param topic: The topic of the channel, or None to set no topic.
        """
        if not self._guild.me.guild_permissions.manage_channels:
            raise PermissionsError("manage_channels")

        if type_ is None:
            type_ = ChannelType.TEXT

        kwargs = {
            "name": name,
            "type": type_.value,
            "permission_overwrites": permission_overwrites,
        }
        if type_ is ChannelType.VOICE:
            kwargs["bitrate"] = bitrate * 1000
            kwargs["user_limit"] = user_limit

        if parent is not None:
            if parent.type != ChannelType.CATEGORY:
                raise CuriousError("Cannot create channel with non-category parent")

            if type_.value == ChannelType.CATEGORY:
                raise CuriousError("Cannot create category channel with category")

            kwargs["parent_id"] = parent.id

        # create a listener so we wait for the WS before editing
        async def _listener(channel: Channel):
            return channel.name == name and channel.guild == self._guild

        async with self._guild._bot.events.wait_for_manager("channel_create", _listener):
            channel_data = await self._guild._bot.http.create_channel(self._guild.id, **kwargs)

        # if it's a text channel and the topic was provided, automatically add it
        if type is ChannelType.TEXT and topic is not None:
            async with self._guild._bot.events.wait_for_manager("channel_update", _listener):
                await self._guild._bot.http.edit_channel(channel_id=channel_data["id"], topic=topic)

        return self._guild._channels[int(channel_data.get("id"))]

    def edit(self, channel: Channel, **kwargs):
        """
        Edits a channel.
        """
        if channel.id not in self._guild._channels:
            raise CuriousError("This channel is not part of this guild")

        return channel.edit(**kwargs)

    def delete(self, channel: Channel):
        """
        Deletes a channel.
        """
        if channel.id not in self._guild._channels:
            raise CuriousError("This channel is not part of this guild")

        return channel.delete()

    async def update_position(
        self,
        tuple_positions: Iterable[Tuple[Channel, int]] = None,
        dict_positions: Dict[Channel, int] = None,
    ):
        """
        Changes the positions of the given channels.
        """

        if not self._guild.me.guild_permissions.manage_channels:
            raise PermissionsError("manage_channels")

        if tuple_positions:
            channels_and_positions = tuple_positions
        elif dict_positions:
            channels_and_positions = dict_positions.items()
        else:
            return

        if isinstance(channels_and_positions, dict):
            channels_and_positions = channels_and_positions.items()

        # in case the iterable is only iterable once, convert it to a list
        channels_and_positions = list(channels_and_positions)

        channels_left = set(chan.id for chan, pos in channels_and_positions if chan.position != pos)

        if not channels_left:
            # nothing to do
            return

        async def listener(old_channel, new_channel):
            """listener that tells us if all channels have been updated"""
            channels_left.discard(new_channel.id)

            return not channels_left

        async with self._guild._bot.events.wait_for_manager("channel_update", listener):
            await self._guild._bot.http.update_channel_positions(
                self._guild.id, [(chan.id, pos) for chan, pos in channels_and_positions]
            )


class GuildRoleWrapper(_WrapperBase):
    """
    A wrapper for roles on a guild. Contains some convenience methods that make role management
    more fluent.
    """

    __slots__ = "_guild", "_roles"

    def __init__(self, guild: "Guild"):
        """
        :param guild: The :class:`.Guild` object that owns this wrapper.
        """
        self._guild = guild

    def __eq__(self, other):
        if not isinstance(other, GuildRoleWrapper):
            return None

        return self._guild.id == other._guild.id and self._guild.roles == other._guild.roles

    @property
    def view(self) -> Mapping[int, Role]:
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._guild._roles)

    def __getitem__(self, key) -> Role:
        default = object()
        got = self.get(key, default=default)
        if got is default:
            raise KeyError(key)

        return got

    def __len__(self) -> int:
        return len(self._guild._roles)

    # overwritten methods from the abc
    def get(self, key: Union[str, int], default: DEFAULT = None) -> Union[Role, DEFAULT]:
        """
        Gets a role by name or ID.

        :param key: The key to use. This can be the ID of the role, or the name of the role.
        :param default: The default value to use, if the role cannot be found.
        :return: A :class:`.Role`, if it was found.
        """
        if isinstance(key, int):
            return self._guild._roles.get(key, default)
        else:
            return self._get_by_name(key, default=default)

    def _get_by_name(self, name: str, default: DEFAULT = None) -> Union[Role, DEFAULT]:
        """
        Gets a role by name.

        :param name: The name of the channel to get.
        :param default: The default value to get, if the role cannot be found.
        :return: A :class:`.Role` if it can be found.
        """
        s = sorted(self._guild._roles.values(), key=lambda c: c.position)
        try:
            return next(filter(lambda r: r.name == name, s))
        except StopIteration:
            return default

    async def create(self, **kwargs) -> Role:
        """
        Creates a new role in this guild.

        :return: A new :class:`.Role`.
        """
        if not self._guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        role_obb = Role(
            client=self._guild._bot, **(await self._guild._bot.http.create_role(self._guild.id))
        )
        self._guild._roles[role_obb.id] = role_obb
        role_obb.guild_id = self._guild.id
        return await role_obb.edit(**kwargs)

    def edit(self, role: Role, **kwargs):
        """
        Edits a role.
        """
        if role.id not in self._guild._roles:
            raise CuriousError("This role is not part of this guild")

        return role.edit(**kwargs)

    def delete(self, role: Role):
        """
        Deletes a role.
        """
        if role.id not in self._guild._roles:
            raise CuriousError("This role is not part of this guild")

        return role.delete()


class GuildEmojiWrapper(_WrapperBase):
    """
    Wrapper for emoji objects for a guild.
    """

    __slots__ = "_guild", "_emojis"

    def __init__(self, guild: "Guild"):
        """
        :param guild: The :class:`.Guild` object that owns this wrapper.
        """
        self._guild = guild

    def __eq__(self, other):
        if not isinstance(other, GuildEmojiWrapper):
            return None

        return self._guild.id == other._guild.id and self._guild.emojis == other._guild.emojis

    @property
    def view(self) -> Mapping[int, Emoji]:
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._guild._emojis)

    def __getitem__(self, key) -> Emoji:
        return self._guild._emojis[key]

    def __len__(self) -> int:
        return len(self._guild._emojis)

    async def create(
        self, *, name: str, image_data: Union[str, bytes], roles: List[Role] = None
    ) -> Emoji:
        """
        Creates a new emoji in this guild.

        :param name: The name of the emoji.
        :param image_data: The bytes image data or the str base64 data for the emoji.
        :param roles: A list of roles this emoji is locked to.
        :return: The :class:`.Emoji` created.
        """
        if isinstance(image_data, bytes):
            image_data = base64ify(image_data)

        if roles is not None:
            roles = [r.id for r in roles]

        emoji_data = await self._guild._bot.http.create_guild_emoji(
            self._guild.id, name=name, image_data=image_data, roles=roles
        )
        emoji = Emoji(**emoji_data, client=self._guild._bot)
        return emoji


class GuildBan:
    """
    Represents a ban in a guild.
    """

    #: The reason for the ban.
    reason: str

    #: The victim of the ban.
    victim: User


if "sphinx" in sys.modules:
    # fuck you
    pass
else:
    GuildBan = dataclass(GuildBan, frozen=True)


class GuildBanContainer(object):
    """
    A container for guild bans.
    """

    def __init__(self, guild: "Guild"):
        self._guild = guild

    async def __aiter__(self) -> AsyncGenerator[GuildBan]:
        if not self._guild.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        bans = await self._guild._bot.http.get_bans(self._guild.id)

        for ban in bans:
            user_data = ban.get("user", None)
            if user_data is None:
                continue

            user = self._guild._bot.state.make_user(user_data)
            self._guild._bot.state._check_decache_user(user.id)
            ban = GuildBan(reason=ban.get("reason", None), user=user)
            yield ban

    async def add(
        self, victim: Union[User, Member], *, delete_message_days: int, reason: str = None
    ) -> GuildBan:
        """
        Bans somebody from the guild.

        This can either ban a :class:`.Member`, in which they must be in the guild.
        Or this can ban a :class:`.User`, which does not need to be in the guild.

        Example for banning a member:

        .. code:: python

            member = guild.members[66237334693085184]
            await guild.ban(member)

        Example for banning a user:

        .. code:: python

            user = await client.get_user(66237334693085184)
            await guild.ban(user)

        :param victim: The :class:`.Member` or :class:`.User` object to ban.
        :param delete_message_days: The number of days to delete messages.
        :param reason: The reason given for banning.
        """
        if not self._guild.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        if isinstance(victim, Member):
            if self._guild.owner == victim:
                raise HierarchyError("Cannot ban the owner")

            if victim.guild_id != self._guild.id:
                raise ValueError("Member must be from this guild (try `member.user` instead!)")

            if victim.top_role >= self._guild.me.top_role:
                raise HierarchyError("Top role is equal to or lower than victim's top role")

            victim_user = victim.user
            victim_id = victim.user.id

        elif isinstance(victim, User):
            victim_user = victim
            victim_id = victim.id

        else:
            raise TypeError("Victim must be a Member or a User")

        await self._guild._bot.http.ban_user(
            guild_id=self._guild.id,
            user_id=victim_id,
            delete_message_days=delete_message_days,
            reason=reason,
        )
        return GuildBan(reason=reason, victim=victim_user)

    async def ban(self, *args, **kwargs) -> "GuildBan":
        """
        Shortcut for :meth:`.GuildBanWrapper.add`.
        """
        return await self.add(*args, **kwargs)

    async def remove(self, user: User, *, reason: str = None) -> None:
        """
        Unbans a user from this guild.
        Example for unbanning the first banned user:

        .. code-block:: python3

            user = next(await guild.get_bans())
            await guild.unban(user)

        To unban an arbitrary user, use :meth:`.Client.get_user`.

        .. code-block:: python3

            user = await client.get_user(66237334693085184)
            await guild.unban(user)

        .. note::

            This does not take :class:`.Member` objects, as members cannot be in a guild and
            banned from the guild.

        :param user: The :class:`.User` to forgive and unban.
        :param reason: The reason given for unbanning.
        """
        if not self._guild.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        forgiven_id = user.id

        await self._guild._bot.http.unban_user(self._guild.id, forgiven_id, reason=reason)

    async def unban(self, *args, **kwargs) -> None:
        """
        Shortcut for :meth:`.GuildBanWrapper.remove`.
        """
        return await self.remove(*args, **kwargs)

    async def flatten(self) -> List[GuildBan]:
        """
        Gets all the bans for this guild.
        """
        return [ban async for ban in self]


class Guild(Dataclass):
    """
    Represents a guild object on Discord.
    """

    __slots__ = (
        "id",
        "unavailable",
        "name",
        "afk_timeout",
        "region",
        "mfa_level",
        "verification_level",
        "notification_level",
        "content_filter_level",
        "features",
        "shard_id",
        "_roles",
        "_members",
        "_channels",
        "_emojis",
        "member_count",
        "_voice_states",
        "_large",
        "_chunks_left",
        "_finished_chunking",
        "icon_hash",
        "splash_hash",
        "owner_id",
        "afk_channel_id",
        "system_channel_id",
        "widget_channel_id",
        "voice_client",
        "channels",
        "roles",
        "emojis",
        "bans",
    )

    valid_embed_styles = {"banner1", "banner3", "banner2", "shield", "banner4"}

    def __init__(self, bot, **kwargs) -> None:
        super().__init__(kwargs.get("id"), bot)

        #: If the guild is unavailable or not.
        #: If this is True, many fields return `None`.
        self.unavailable = kwargs.get("unavailable", False)

        # Placeholder values.
        #: The name of this guild.
        self.name: str = None  # noqa

        #: The icon hash of this guild.
        #: Used to construct the icon URL later.
        self.icon_hash: Optional[str] = None  # noqa

        #: The splash hash of this guild.
        #: Used to construct the splash URL later.
        self.splash_hash: str = None  # noqa

        #: The AFK channel ID of this guild.
        self.afk_channel_id: int = 0

        #: The ID of the system channel for this guild.
        #: This is where welcome messages and the likes are sent.
        #: Effective replacement for default channel for bots.
        self.system_channel_id: int = 0

        #: The widget channel ID for this guild.
        self.widget_channel_id: int = 0

        #: The owner ID of this guild.
        self.owner_id: int = 0

        #: The AFK timeout for this guild. None if there's no AFK timeout.
        self.afk_timeout: int = 0

        #: The voice region of this guild.
        self.region: str = None  # noqa

        #: The features this guild has.
        self.features: List[str] = None  # noqa

        #: The MFA level of this guild.
        self.mfa_level = MFALevel.DISABLED
        #: The verification level of this guild.
        self.verification_level = VerificationLevel.NONE
        #: The notification level of this guild.
        self.notification_level = NotificationLevel.ALL_MESSAGES
        #: The content filter level of this guild.
        self.content_filter_level = ContentFilterLevel.SCAN_NONE

        #: The shard ID this guild is associated with.
        self.shard_id: int = None  # noqa

        #: The roles that this guild has.
        self._roles: MutableMapping[int, Role] = {}
        #: The members of this guild.
        self._members: MutableMapping[int, Member] = {}
        #: The channels of this guild.
        self._channels: MutableMapping[int, Channel] = {}
        #: The emojis that this guild has.
        self._emojis: MutableMapping[int, Emoji] = {}
        #: The voice states that this guild has.
        self._voice_states: MutableMapping[int, VoiceState] = {}

        #: The number of numbers this guild has.
        #: This is automatically updated.
        self.member_count = 0  # type: int

        #: Is this guild a large guild according to Discord?
        self._large: bool = False

        #: Has this guild finished chunking?
        self._finished_chunking = trio.Event()
        self._chunks_left = 0

        #: The current voice client associated with this guild.
        self.voice_client = None

        #: The :class:`.GuildChannelWrapper` that wraps the channels in this Guild.
        self.channels = GuildChannelWrapper(self)
        #: The :class:`.GuildRoleWrapper` that wraps the roles in this Guild.
        self.roles = GuildRoleWrapper(self)
        #: The :class:`.GuildEmojiWrapper` that wraps the emojis in this Guild.
        self.emojis = GuildEmojiWrapper(self)
        #: The :class:`.GuildBanContainer` for this Guild.
        self.bans = GuildBanContainer(self)

    def _copy(self) -> "Guild":
        obb = copy.copy(self)
        obb.channels = GuildChannelWrapper(obb)
        obb.roles = GuildRoleWrapper(obb)
        obb.emojis = GuildEmojiWrapper(obb)
        obb.bans = GuildRoleWrapper(obb)
        obb._channels = self._channels.copy()  # noqa
        obb._roles = self._roles.copy()  # noqa
        obb._emojis = self._roles.copy()  # noqa
        obb._members = self._members.copy()  # noqa
        obb._voice_states = self._voice_states.copy()  # noqa
        return obb

    def __repr__(self) -> str:
        return "<Guild id='{}' name='{}' members='{}'>".format(
            self.id, self.name, self.member_count
        )

    def __str__(self) -> str:
        return repr(self)

    @property
    def members(self) -> Mapping[int, Member]:
        """
        :return: A mapping of :class:`.Member` that represent members on this guild.
        """
        return MappingProxyType(self._members)

    @property
    def voice_states(self) -> Mapping[int, VoiceState]:
        """
        :return: A mapping of :class:`.VoiceState` that represent voice states in this guild.
        """
        return MappingProxyType(self._voice_states)

    @property
    def owner(self) -> Member:
        """
        :return: A :class:`.Member` object that represents the owner of this guild.
        """
        return self._members[self.owner_id]

    @property
    def me(self) -> Member:
        """
        :return: A :class:`.Member` object that represents the current user in this guild.
        """
        return self._members[self._bot.user.id]

    @property
    def default_role(self) -> Role:
        """
        :return: A :class:`.Role` that represents the default role of this guild.
        """
        return self.roles[self.id]

    @property
    def system_channel(self) -> Optional[Channel]:
        """
        :return: A :class:`.Channel` that represents the system channel for this guild.
        """
        try:
            return self._channels[self.system_channel_id]
        except KeyError:
            return None

    @property
    def afk_channel(self) -> Optional[Channel]:
        """
        :return: A :class:`.Channel` representing the AFK channel for this guild.
        """
        try:
            return self._channels[self.afk_channel_id]
        except IndexError:
            return None

    @property
    def embed_url(self) -> str:
        """
        Gets the default embed url for this guild.
        If the widget is not enabled, this endpoint will 404.

        :return: The embed URL for this guild.
        """
        return (Endpoints.GUILD_BASE + "/embed.png").format(guild_id=self.id)

    # for parity with inviteguild
    @property
    def presence_count(self) -> int:
        """
        :return: The number of members with a non-Invisible presence.
        """
        return sum(1 for member in self._members.values() if member.status is not Status.OFFLINE)

    def get_embed_url(self, *, style: str = "banner1") -> str:
        """
        Gets an embed URL for this guild in a specified style.

        :param style: The style to get.
        :return: The embed URL for this guild.
        """
        if style not in self.valid_embed_styles:
            raise ValueError("Style must be in {}".format(self.valid_embed_styles))

        return self.embed_url + "?style={}".format(style)

    def search_for_member(
        self, *, name: str = None, discriminator: str = None, full_name: str = None
    ) -> Optional[Member]:
        """
        Searches for a member.

        :param name: The username or nickname of the member.
        :param discriminator: The discriminator of the member.
        :param full_name: The full name (i.e. username#discrim) of the member. Optional; will be \
            split up into the correct parameters.

        .. warning::

            Using a username and discriminator pair is most accurate when finding a user; a
            nickname pair or not providing one of the arguments might not find the right member.

        :return: A :class:`.Member` that matched, or None if no matches were found.
        """
        if full_name is not None:
            if "#" in full_name:
                sp = full_name.split("#", 1)
                return self.search_for_member(name=sp[0], discriminator=sp[1])
            else:
                # usually a mistake
                return self.search_for_member(name=full_name)

        # coerce into a proper string
        if isinstance(discriminator, int):
            discriminator = "{:04d}".format(discriminator)

        for member in self._members.values():
            # ensure discrim matches first
            if discriminator is not None and discriminator != member.user.discriminator:
                continue

            if member.user.username == name:
                return member

            if member.nickname == name:
                return member

    # creation methods
    def start_chunking(self) -> None:
        """
        Marks a guild to start guild chunking.

        This will clear the chunking event, and calculate the number of member chunks required.
        """
        self._finished_chunking.clear()
        self._chunks_left = ceil(self.member_count / 1000)

    async def wait_until_chunked(self) -> None:
        """
        Waits until the guild has finished chunking.

        Useful for when you join a big guild.
        """
        await self._finished_chunking.wait()

    def _handle_member_chunk(self, members: list):
        """
        Handles a chunk of members.

        :param members: A list of member data dictionaries as returned from Discord.
        """
        if self._chunks_left >= 1:
            # We have a new chunk, so decrement the number left.
            self._chunks_left -= 1

        for member_data in members:
            member_id = int(member_data["user"]["id"])
            if member_id in self._members:
                member_obj = self._members[member_id]
            else:
                member_obj = Member(self._bot, **member_data)
                self._members[member_obj.id] = member_obj

            member_obj.nickname = member_data.get("nick", member_obj.nickname)
            member_obj.guild_id = self.id

    def _handle_emojis(self, emojis: List[dict]):
        """
        Handles the emojis for this guild.

        :param emojis: A list of emoji objects from Discord.
        """
        for emoji in emojis:
            emoji_obj = Emoji(**emoji, client=self._bot)
            self._emojis[emoji_obj.id] = emoji_obj
            emoji_obj.guild_id = self.id

    def from_guild_create(self, **data) -> "Guild":
        """
        Populates the fields from a GUILD_CREATE event.

        :param data: The GUILD_CREATE data to use.
        """
        self.unavailable = data.get("unavailable", False)

        if self.unavailable:
            # We can't use any of the extra data here, so don't bother.
            return self

        self.name = data["name"]
        self.icon_hash = data.get("icon")
        self.splash_hash = data.get("splash")
        self.owner_id = int(data["owner_id"])
        self._large = data.get("large", None)
        self.features = data.get("features", [])
        self.region = data.get("region")

        afk_channel_id = data.get("afk_channel_id", 0)
        if afk_channel_id:
            afk_channel_id = int(afk_channel_id)

        self.afk_channel_id = afk_channel_id
        self.afk_timeout = data.get("afk_timeout")

        system_channel_id = data.get("system_channel_id", 0)
        if system_channel_id:
            system_channel_id = int(system_channel_id)

        self.system_channel_id = system_channel_id

        self.verification_level = VerificationLevel(data.get("verification_level", 0))
        self.mfa_level = MFALevel(data.get("mfa_level", 0))
        self.notification_level = NotificationLevel(data.get("default_message_notifications", 0))
        self.content_filter_level = ContentFilterLevel(data.get("explicit_content_filter", 0))

        self.member_count = data.get("member_count", 0)

        # Create all the Role objects for the server.
        for role_data in data.get("roles", []):
            role_obj = Role(self._bot, **role_data)
            role_obj.guild_id = self.id
            self._roles[role_obj.id] = role_obj

        # Create all the Member objects for the server.
        self._handle_member_chunk(data.get("members", []))

        for presence in data.get("presences", []):
            member_id = int(presence["user"]["id"])
            member_obj = self._members.get(member_id)

            if not member_obj:
                continue

            member_obj.presence = Presence(**presence)

        # Create all of the channel objects.
        for channel_data in data.get("channels", []):
            channel_obj = Channel(self._bot, **channel_data)
            self._channels[channel_obj.id] = channel_obj
            channel_obj.guild_id = self.id
            channel_obj._update_overwrites(
                channel_data.get("permission_overwrites", []),
            )

        # Create all of the voice states.
        for vs_data in data.get("voice_states", []):
            user_id = int(vs_data.get("user_id", 0))
            member = self.members.get(user_id)
            if not member:
                # o well
                continue

            voice_state = VoiceState(**vs_data, client=self._bot)
            self._voice_states[voice_state.user_id] = voice_state

            vs_channel = self._channels.get(int(vs_data.get("channel_id", 0)))
            if vs_channel is not None:
                voice_state.channel_id = vs_channel.id
                voice_state.guild_id = self.id

        # delegate to other function
        self._handle_emojis(data.get("emojis", []))

    @property
    def large(self) -> bool:
        """
        :return: If this guild is large or not (>= 250 members).
        """
        if self._large is not None:
            return self._large

        return self.member_count >= 250

    @property
    def invites(self) -> AsyncIterator[Invite]:
        """
        :return: A class:`.AsyncIteratorWrapper` that yields :class:`.Invite` objects for this
            guild.
        """
        return AsyncIteratorWrapper(self.get_invites)

    @property
    def icon_url(self) -> str:
        """
        :return: The icon URL for this guild, or None if one isn't set.
        """
        if self.icon_hash:
            return "https://cdn.discordapp.com/icons/{}/{}.webp".format(self.id, self.icon_hash)

    @property
    def splash_url(self) -> str:
        """
        :return: The splash URL for this guild, or None if one isn't set.
        """
        if self.splash_hash:
            return "https://cdn.discordapp.com/splashes/{}/{}.webp".format(
                self.id, self.splash_hash
            )

    # Guild methods.
    async def leave(self) -> None:
        """
        Leaves the guild.
        """
        await self._bot.http.leave_guild(self.id)

    async def get_invites(self) -> List[Invite]:
        """
        Gets the invites for this guild.
        :return: A list :class:`.Invite` objects.
        """
        invites = await self._bot.http.get_invites_for(self.id)
        invites = [Invite(self._bot, **i) for i in invites]

        try:
            invite = await self.get_vanity_invite()
            invites.insert(0, invite)
        except (CuriousError, HTTPException):
            pass

        return invites

    async def kick(self, victim: Member):
        """
        Kicks somebody from the guild.

        :param victim: The :class:`.Member` to kick.
        """
        if not self.me.guild_permissions.kick_members:
            raise PermissionsError("kick_members")

        if self.owner == victim:
            raise HierarchyError("Cannot kick the owner")

        if victim.guild != self:
            raise ValueError("Member must be from this guild (try `member.user` instead)")

        if victim.top_role >= self.me.top_role:
            raise HierarchyError("Top role is equal to or lower than victim's top role")

        victim_id = victim.user.id

        await self._bot.http.kick_member(self.id, victim_id)

    async def get_webhooks(self) -> List[Webhook]:
        """
        Gets the webhooks for this guild.

        :return: A list of :class:`.Webhook` objects for the guild.
        """
        webhooks = await self._bot.http.get_webhooks_for_guild(self.id)
        obbs = []

        for webhook in webhooks:
            obbs.append(self._bot.state.make_webhook(webhook))

        return obbs

    async def delete_webhook(self, webhook: Webhook):
        """
        Deletes a webhook in this guild.

        :param webhook: The :class:`.Webhook` to delete.
        """
        if not self.me.guild_permissions.manage_webhooks:
            raise PermissionsError("manage_webhooks")

        await self._bot.http.delete_webhook(webhook.id)

    async def change_role_positions(
        self,
        tuple_positions: Iterable[Tuple[Role, int]] = None,
        dict_positions: Dict[Role, int] = None,
    ):
        """
        Changes the position of N roles.

        :param tuple_positions: An iterable of (role, new_position).
        :param dict_positions: A dict of {role: position}.
        """

        if not self.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        if tuple_positions:
            roles = tuple_positions
        elif dict_positions:
            roles = dict_positions.items()
        else:
            raise ValueError("Must pass either tuple_positions or dict_positionns")

        to_send = []
        for r, new_position in roles:
            if new_position >= self.me.top_role.position:
                raise HierarchyError("Cannot move role above our top role")

            to_send.append((str(r.id), new_position))

        to_send = [(str(r.id), new_position) for (r, new_position) in roles]
        await self._bot.http.edit_role_positions(to_send)

    async def change_voice_state(
        self, member: Member, *, deaf: bool = None, mute: bool = None, channel: Channel = None
    ):
        """
        Changes the voice state of a member.

        :param member: The :class:`.Member` to change the voice state of.
        :param deaf: Should this member be deafened?
        :param mute: Should this member be muted?
        :param channel: The channel to move this member to.
        """
        if member.voice is None:
            raise CuriousError("Cannot change voice state of member not in voice")

        channel_id = channel.id if channel is not None else None
        await self._bot.http.edit_member_voice_state(
            self.id, member.id, deaf=deaf, mute=mute, channel_id=channel_id
        )
        return member.voice

    async def modify_guild(
        self,
        *,
        afk_channel: Channel = None,
        verification_level: VerificationLevel = None,
        content_filter_level: ContentFilterLevel = None,
        notification_level: NotificationLevel = None,
        **kwargs,
    ):
        """
        Edits this guild.

        For a list of available arguments, see
        https://discordapp.com/developers/docs/resources/guild#modify-guild.

        :param afk_channel: The :class:`.Channel` that represents the AFK voice channel.
        :param verification_level: The :class:`.VerificationLevel` to use for this guild.
        :param content_filter_level: The :class:`.ContentFilterLevel` to use for this guild.
        :param notification_level: The :class:`.NotificationLevel` to use for this guild.
        """
        if not self.me.guild_permissions.manage_server:
            raise PermissionsError("manage_server")

        if afk_channel is not None:
            kwargs["afk_channel_id"] = afk_channel.id

        if verification_level is not None:
            kwargs["verification_level"] = verification_level.value

        if notification_level is not None:
            kwargs["default_message_notifications"] = notification_level.value

        if content_filter_level is not None:
            kwargs["explicit_content_filter"] = content_filter_level.value

        await self._bot.http.edit_guild(self.id, **kwargs)
        return self

    async def change_icon(self, icon_content: bytes):
        """
        Changes the icon for this guild.

        :param icon_content: The bytes that represent the icon of the guild.
        """
        if not self.me.guild_permissions.manage_server:
            raise PermissionsError("manage_server")

        image = base64ify(icon_content)
        await self._bot.http.edit_guild(self.id, icon_content=image)

    async def upload_icon(self, path: PathLike):
        """
        Uploads a new icon for the guild.

        :param path: A path-like object to use to upload.
        """
        with open(path, "rb") as f:
            return await self.change_icon(f.read())

    async def get_vanity_invite(self) -> Optional[Invite]:
        """
        Gets the vanity :class:`.Invite` for this guild.

        :return: The :class:`.Invite` that corresponds with this guild, if it has one.
        """
        if "vanity-url" not in self.features:
            return None

        try:
            resp = await self._bot.http.get_vanity_url(self.id)
        except HTTPException as e:
            if e.error_code != 50020:
                raise
            else:
                return None

        code = resp.get("code", None)
        if code is None:
            return None

        invite_data = await self._bot.http.get_invite(code)
        invite = Invite(self._bot, **invite_data)

        return invite

    async def set_vanity_invite(self, url: str) -> Optional[Invite]:
        """
        Sets the vanity :class:`.Invite` for this guild.

        :param url: The code to use for this guild.
        :return: The :class:`.Invite` produced.
        """
        if "vanity-url" not in self.features:
            raise CuriousError("This guild has no vanity URL")

        try:
            resp = await self._bot.http.edit_vanity_url(self.id, url)
        except HTTPException as e:
            if e.error_code != 50020:
                raise

            raise CuriousError("This guild has no vanity URL")

        code = resp.get("code", None)
        if code is None:
            return None

        invite_data = await self._bot.http.get_invite(code)
        invite = Invite(self._bot, **invite_data)

        return invite
