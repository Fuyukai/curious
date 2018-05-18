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
import sys
from math import ceil

import abc
import collections
import copy
import datetime
import enum
import multio
import typing
from dataclasses import dataclass
from os import PathLike
from types import MappingProxyType

from curious.core.httpclient import Endpoints
from curious.dataclasses import channel as dt_channel, emoji as dt_emoji, invite as dt_invite, \
    member as dt_member, permissions as dt_permissions, role as dt_role, \
    search as dt_search, user as dt_user, voice_state as dt_vs, webhook as dt_webhook
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.presence import Presence, Status
from curious.exc import CuriousError, HTTPException, HierarchyError, PermissionsError
from curious.util import AsyncIteratorWrapper, base64ify, deprecated

default_var = typing.TypeVar("T")


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

    def can_speak(self, member: 'dt_member.Member') -> bool:
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
            if member.joined_at < dt:
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


class _WrapperBase(collections.Mapping, collections.Iterable):
    """
    Represents the base class for a wrapper object.
    """

    __slots__ = ()

    @property
    @abc.abstractmethod
    def view(self) -> 'typing.Mapping[int, Dataclass]':
        """
        Represents a read-only view for this wrapper.
        """

    def __iter__(self) -> typing.Iterator[typing.Any]:
        return iter(self.view.keys())

    def __repr__(self) -> str:
        return "<{} items='{}'>".format(type(self).__name__, self.view)


class GuildChannelWrapper(_WrapperBase):
    """
    A wrapper for channels on a guild. This provides some convenience methods which make channel
    management more fluent.
    """
    __slots__ = "_guild", "_channels"

    def __init__(self, guild: 'Guild',
                 channels: 'typing.MutableMapping[int, dt_channel.Channel]'):
        """
        :param guild: The :class:`.Guild` object that owns this wrapper.
        :param channels: The dictionary of channels that this wrapper contains.
        """
        self._guild = guild
        self._channels = channels

    @property
    def view(self) -> 'typing.Mapping[int, dt_channel.Channel]':
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._channels)

    def __getitem__(self, key) -> 'dt_channel.Channel':
        default = object()
        got = self.get(key, default=default)
        if got is default:
            raise KeyError(key)

        return got

    def __len__(self) -> int:
        return len(self._channels)

    # overwritten methods from the abc
    def get(self, key: typing.Union[str, int], default: default_var = None) \
            -> 'typing.Union[dt_channel.Channel, default_var]':
        """
        Gets a channel by name or ID.

        :param key: The key to use. This can be the ID of the channel, or the name of the channel.
        :param default: The default value to use, if the channel cannot be found.
        :return: A :class:`.Channel`, if it was found.
        """
        if isinstance(key, int):
            return self._channels.get(key, default)
        else:
            return self._get_by_name(key, default=default)

    def _get_by_name(self, name: str, default: default_var = None) \
            -> 'typing.Union[dt_channel.Channel, default_var]':
        """
        Gets a channel by name.

        .. warning::

            This will return the first channel in the channel list. If you want to get a channel
            in a specific category, use :meth:`.Channel.get_by_name`

        :param name: The name of the channel to get.
        :param default: The default value to get, if the channel cannot be found.
        :return: A :class:`.Channel` if it can be found.
        """
        s = sorted(self._channels.values(), key=lambda c: c.position)
        try:
            return next(filter(lambda ch: ch.name == name, s))
        except StopIteration:
            return default

    async def create(self, name: str, type_: 'dt_channel.ChannelType' = None,
                     permission_overwrites: 'typing.List[dt_permissions.Overwrite]' = None,
                     *,
                     parent: 'dt_channel.Channel' = None,
                     bitrate: int = 64, user_limit: int = 0,
                     topic: str = None) -> 'dt_channel.Channel':
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
            type_ = dt_channel.ChannelType.TEXT

        kwargs = {
            "name": name,
            "type": type_.value,
            "permission_overwrites": permission_overwrites,
        }
        if type_ is dt_channel.ChannelType.VOICE:
            kwargs["bitrate"] = bitrate
            kwargs["user_limit"] = user_limit

        if parent is not None:
            if parent.type != dt_channel.ChannelType.CATEGORY:
                raise CuriousError("Cannot create channel with non-category parent")

            if type_.value == dt_channel.ChannelType.CATEGORY:
                raise CuriousError("Cannot create category channel with category")

            kwargs["parent_id"] = parent.id

        # create a listener so we wait for the WS before editing
        async def _listener(channel: dt_channel.Channel):
            if channel.name == name and channel.guild == self._guild:
                return True

            return False

        async with self._guild._bot.events.wait_for_manager("channel_update", _listener):
            channel_data = await self._guild._bot.http.create_channel(self._guild.id, **kwargs)
            # if it's a text channel and the topic was provided, automatically add it
            if type is dt_channel.ChannelType.TEXT and topic is not None:
                await self._guild._bot.http.edit_channel(channel_id=channel_data["id"], topic=topic)

        return self._channels[int(channel_data.get("id"))]

    def edit(self, channel: 'dt_channel.Channel', **kwargs):
        """
        Edits a channel.
        """
        if channel.id not in self._channels:
            raise CuriousError("This channel is not part of this guild")

        return channel.edit(**kwargs)

    def delete(self, channel: 'dt_channel.Channel'):
        """
        Deletes a channel.
        """
        if channel.id not in self._channels:
            raise CuriousError("This channel is not part of this guild")

        return channel.delete()


class GuildRoleWrapper(_WrapperBase):
    """
    A wrapper for roles on a guild. Contains some convenience methods that make role management
    more fluent.
    """

    __slots__ = "_guild", "_roles"

    def __init__(self, guild: 'Guild',
                 roles: 'typing.MutableMapping[int, dt_role.Role]'):
        """
        :param guild: The :class:`.Guild` object that owns this wrapper.
        :param roles: The dictionary of roles that this wrapper contains.
        """
        self._guild = guild
        self._roles = roles

    @property
    def view(self) -> 'typing.Mapping[int, dt_role.Role]':
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._roles)

    def __getitem__(self, key) -> 'dt_role.Role':
        default = object()
        got = self.get(key, default=default)
        if got is default:
            raise KeyError(key)

        return got

    def __len__(self) -> int:
        return len(self._roles)

    # overwritten methods from the abc
    def get(self, key: typing.Union[str, int], default: default_var = None) \
            -> 'typing.Union[dt_role.Role, default_var]':
        """
        Gets a role by name or ID.

        :param key: The key to use. This can be the ID of the role, or the name of the role.
        :param default: The default value to use, if the role cannot be found.
        :return: A :class:`.Role`, if it was found.
        """
        if isinstance(key, int):
            return self._roles.get(key, default)
        else:
            return self._get_by_name(key, default=default)

    def _get_by_name(self, name: str, default: default_var = None) \
            -> 'typing.Union[dt_role.Role, default_var]':
        """
        Gets a role by name.

        :param name: The name of the channel to get.
        :param default: The default value to get, if the role cannot be found.
        :return: A :class:`.Role` if it can be found.
        """
        s = sorted(self._roles.values(), key=lambda c: c.position)
        try:
            return next(filter(lambda r: r.name == name, s))
        except StopIteration:
            return default

    async def create(self, **kwargs) -> 'dt_role.Role':
        """
        Creates a new role in this guild.

        :return: A new :class:`.Role`.
        """
        if not self._guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        role_obb = dt_role.Role(client=self._guild._bot,
                                **(await self._guild._bot.http.create_role(self._guild.id)))
        self._roles[role_obb.id] = role_obb
        role_obb.guild_id = self._guild.id
        return await role_obb.edit(**kwargs)

    def edit(self, role: 'dt_role.Role', **kwargs):
        """
        Edits a role.
        """
        if role.id not in self._roles:
            raise CuriousError("This role is not part of this guild")

        return role.edit(**kwargs)

    def delete(self, role: 'dt_role.Role'):
        """
        Deletes a role.
        """
        if role.id not in self._roles:
            raise CuriousError("This role is not part of this guild")

        return role.delete()


class GuildEmojiWrapper(_WrapperBase):
    """
    Wrapper for emoji objects for a guild.
    """
    __slots__ = "_guild", "_emojis"

    def __init__(self, guild: 'Guild',
                 emojis: 'typing.MutableMapping[int, dt_emoji.Emoji]'):
        """
        :param guild: The :class:`.Guild` object that owns this wrapper.
        :param emojis: The dictionary of emojis that this wrapper contains.
        """
        self._guild = guild
        self._emojis = emojis

    @property
    def view(self) -> 'typing.Mapping[int, dt_emoji.Emoji]':
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._emojis)

    def __getitem__(self, key) -> 'dt_emoji.Emoji':
        return self._emojis[key]

    def __len__(self) -> int:
        return len(self._emojis)

    async def create(self, *,
                     name: str, image_data: typing.Union[str, bytes],
                     roles: 'typing.List[dt_role.Role]' = None) -> 'dt_emoji.Emoji':
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

        emoji_data = await self._guild._bot.http.create_guild_emoji(self._guild.id,
                                                                    name=name,
                                                                    image_data=image_data,
                                                                    roles=roles)
        emoji = dt_emoji.Emoji(**emoji_data, client=self._guild._bot)
        return emoji


class GuildBan:
    """
    Represents a ban in a guild.
    """
    #: The reason for the ban.
    reason: str

    #: The victim of the ban.
    victim: 'dt_user.User'


if 'sphinx' in sys.modules:
    # fuck you
    pass
else:
    GuildBan = dataclass(GuildBan, frozen=True)


class GuildBanContainer(object):
    """
    A container for guild bans.
    """

    def __init__(self, guild: 'Guild'):
        self._guild = guild

    async def __aiter__(self) -> 'typing.AsyncGenerator[GuildBan]':
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

    async def add(self, victim: 'typing.Union[dt_user.User, dt_member.Member]', *,
                  delete_message_days: int, reason: str = None) -> GuildBan:
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

        if isinstance(victim, dt_member.Member):
            if self._guild.owner == victim:
                raise HierarchyError("Cannot ban the owner")

            if victim.guild_id != self._guild.id:
                raise ValueError("Member must be from this guild (try `member.user` instead!)")

            if victim.top_role >= self._guild.me.top_role:
                raise HierarchyError("Top role is equal to or lower than victim's top role")

            victim_user = victim.user
            victim_id = victim.user.id

        elif isinstance(victim, dt_user.User):
            victim_user = victim
            victim_id = victim.id

        else:
            raise TypeError("Victim must be a Member or a User")

        await self._guild._bot.http.ban_user(guild_id=self._guild.id, user_id=victim_id,
                                             delete_message_days=delete_message_days,
                                             reason=reason)
        return GuildBan(reason=reason, victim=victim_user)

    async def ban(self, *args, **kwargs) -> 'GuildBan':
        """
        Shortcut for :meth:`.GuildBanWrapper.add`.
        """
        return await self.add(*args, **kwargs)

    async def remove(self, user: 'dt_user.User', *,
                     reason: str = None) -> None:
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

    async def flatten(self) -> 'typing.List[GuildBan]':
        """
        Gets all the bans for this guild.
        """
        return [ban async for ban in self]


class Guild(Dataclass):
    """
    Represents a guild object on Discord.
    """

    __slots__ = (
        "id", "unavailable", "name", "afk_timeout", "region",
        "mfa_level", "verification_level", "notification_level", "content_filter_level", "features",
        "shard_id", "_roles", "_members", "_channels", "_emojis", "member_count", "_voice_states",
        "_large", "_chunks_left", "_finished_chunking", "icon_hash", "splash_hash",
        "owner_id", "afk_channel_id", "system_channel_id", "widget_channel_id",
        "voice_client",
        "channels", "roles", "emojis", "bans",
    )

    valid_embed_styles = {'banner1', 'banner3', 'banner2', 'shield', 'banner4'}

    def __init__(self, bot, **kwargs) -> None:
        super().__init__(kwargs.get("id"), bot)

        #: If the guild is unavailable or not.
        #: If this is True, many fields return `None`.
        self.unavailable = kwargs.get("unavailable", False)

        # Placeholder values.
        #: The name of this guild.
        self.name = None  # type: str

        #: The icon hash of this guild.
        #: Used to construct the icon URL later.
        self.icon_hash = None  # type: str

        #: The splash hash of this guild.
        #: Used to construct the splash URL later.
        self.splash_hash = None  # type: str

        #: The AFK channel ID of this guild.
        self.afk_channel_id = None  # type: int

        #: The ID of the system channel for this guild.
        #: This is where welcome messages and the likes are sent.
        #: Effective replacement for default channel for bots.
        self.system_channel_id = None  # type: int

        #: The widget channel ID for this guild.
        self.widget_channel_id = None  # type: int

        #: The owner ID of this guild.
        self.owner_id = None  # type: int

        #: The AFK timeout for this guild. None if there's no AFK timeout.
        self.afk_timeout = None  # type: int

        #: The voice region of this guild.
        self.region = None  # type: str

        #: The features this guild has.
        self.features = None  # type: typing.List[str]

        #: The MFA level of this guild.
        self.mfa_level = MFALevel.DISABLED
        #: The verification level of this guild.
        self.verification_level = VerificationLevel.NONE
        #: The notification level of this guild.
        self.notification_level = NotificationLevel.ALL_MESSAGES
        #: The content filter level of this guild.
        self.content_filter_level = ContentFilterLevel.SCAN_NONE

        #: The shard ID this guild is associated with.
        self.shard_id = None  # type: int

        #: The roles that this guild has.
        self._roles = {}
        #: The members of this guild.
        self._members = {}
        #: The channels of this guild.
        self._channels = {}
        #: The emojis that this guild has.
        self._emojis = {}
        #: The voice states that this guild has.
        self._voice_states = {}

        #: The number of numbers this guild has.
        #: This is automatically updated.
        self.member_count = 0  # type: int

        #: Is this guild a large guild according to Discord?
        self._large = None  # type: bool

        #: Has this guild finished chunking?
        self._finished_chunking = multio.Event()
        self._chunks_left = 0

        #: The current voice client associated with this guild.
        self.voice_client = None

        #: The :class:`.GuildChannelWrapper` that wraps the channels in this Guild.
        self.channels = GuildChannelWrapper(self, self._channels)
        #: The :class:`.GuildRoleWrapper` that wraps the roles in this Guild.
        self.roles = GuildRoleWrapper(self, self._roles)
        #: The :class:`.GuildEmojiWrapper` that wraps the emojis in this Guild.
        self.emojis = GuildEmojiWrapper(self, self._emojis)
        #: The :class:`.GuildBanContainer` for this Guild.
        self.bans = GuildBanContainer(self)

    def _copy(self) -> 'Guild':
        return copy.copy(self)

    def __repr__(self) -> str:
        return "<Guild id='{}' name='{}' members='{}'>".format(self.id, self.name,
                                                               self.member_count)

    def __str__(self) -> str:
        return repr(self)

    @property
    def members(self) -> 'typing.Mapping[int, dt_member.Member]':
        """
        :return: A mapping of :class:`.Member` that represent members on this guild.
        """
        return MappingProxyType(self._members)

    @property
    def owner(self) -> 'typing.Union[dt_member.Member, None]':
        """
        :return: A :class:`.Member` object that represents the owner of this guild.
        """
        try:
            return self._members[self.owner_id]
        except KeyError:
            return None

    @property
    def me(self) -> 'typing.Union[dt_member.Member, None]':
        """
        :return: A :class:`.Member` object that represents the current user in this guild.
        """
        try:
            return self._members[self._bot.user.id]
        except KeyError:
            return None

    @property
    def default_role(self) -> 'typing.Union[dt_role.Role, None]':
        """
        :return: A :class:`.Role` that represents the default role of this guild.
        """
        try:
            return self.roles[self.id]
        except KeyError:
            return None

    @property
    def system_channel(self) -> 'typing.Union[dt_channel.Channel, None]':
        """
        :return: A :class:`.Channel` that represents the system channel for this guild.
        """
        try:
            return self._channels[self.system_channel_id]
        except KeyError:
            return None

    @property
    def afk_channel(self) -> 'typing.Union[dt_channel.Channel, None]':
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

    # Presence methods
    def members_with_status(self, status: Status) \
            -> 'typing.Generator[dt_member.Member, None, None]':
        """
        A generator that returns the members that match the specified status.
        """
        for member in self.members.values():
            if member.status == status:
                yield member

    @property
    def online_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of online :class:`.Member` objects.
        """
        return self.members_with_status(Status.ONLINE)

    @property
    def idle_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of idle :class:`.Member` objects.
        """
        return self.members_with_status(Status.IDLE)

    @property
    def dnd_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of DnD :class:`.Member` objects.
        """
        return self.members_with_status(Status.DND)

    @property
    def offline_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of offline/invisible :class:`.Member` objects.
        """
        return self.members_with_status(Status.OFFLINE)

    @property
    def search(self) -> 'dt_search.SearchQuery':
        """
        :return: A :class:`.SearchQuery` that can be used to search this guild's messages.
        """
        return dt_search.SearchQuery(guild=self)

    def get_embed_url(self, *, style: str = "banner1") -> str:
        """
        Gets an embed URL for this guild in a specified style.
        
        :param style: The style to get. 
        :return: The embed URL for this guild.
        """
        if style not in self.valid_embed_styles:
            raise ValueError("Style must be in {}".format(self.valid_embed_styles))

        return self.embed_url + "?style={}".format(style)

    def search_for_member(self, *, name: str = None, discriminator: str = None,
                          full_name: str = None):
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

    @deprecated(since="0.7.0", see_instead=search_for_member, removal="0.9.0")
    def find_member(self, search_str: str) -> 'dt_member.Member':
        """
        Attempts to find a member in this guild by name#discrim.
        This will also search nicknames.

        The discriminator is optional, but if provided allows better matching.

        :param search_str: The name#discrim pair to search for.
        :return: A :class:`.Member` object that represents the member, or None if no member \
                could be found.
        """
        sp = search_str.rsplit("#", 1)
        if len(sp) == 1:
            # Member name only :(
            predicate = lambda member: member.user.name == sp[0] or member.nickname == sp[0]
        else:
            # Discriminator too!
            # Don't check nicknames for this.
            predicate = lambda member: member.user.name == sp[0] \
                                       and member.user.discriminator == sp[1]

        filtered = filter(predicate, self.members.values())
        return next(filtered, None)

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
                member_obj = dt_member.Member(self._bot, **member_data)
                self._members[member_obj.id] = member_obj

            member_obj.nickname = member_data.get("nick", member_obj.nickname)
            member_obj.guild_id = self.id

    def _handle_emojis(self, emojis: typing.List[dict]):
        """
        Handles the emojis for this guild.
        
        :param emojis: A list of emoji objects from Discord.
        """
        for emoji in emojis:
            emoji_obj = dt_emoji.Emoji(**emoji, client=self._bot)
            self._emojis[emoji_obj.id] = emoji_obj
            emoji_obj.guild_id = self.id

    def from_guild_create(self, **data: dict) -> 'Guild':
        """
        Populates the fields from a GUILD_CREATE event.

        :param data: The GUILD_CREATE data to use.
        """
        self.unavailable = data.get("unavailable", False)

        if self.unavailable:
            # We can't use any of the extra data here, so don't bother.
            return self

        self.name = data.get("name")  # type: str
        self.icon_hash = data.get("icon")  # type: str
        self.splash_hash = data.get("splash")  # type: str
        self.owner_id = int(data.get("owner_id", 0)) or None  # type: int
        self._large = data.get("large", None)
        self.features = data.get("features", [])
        self.region = data.get("region")

        afk_channel_id = data.get("afk_channel_id", 0)
        if afk_channel_id:
            afk_channel_id = int(afk_channel_id)

        self.afk_channel_id = afk_channel_id
        self.afk_timeout = data.get("afk_timeout")

        self.verification_level = VerificationLevel(data.get("verification_level", 0))
        self.mfa_level = MFALevel(data.get("mfa_level", 0))
        self.notification_level = NotificationLevel(data.get("default_message_notifications", 0))
        self.content_filter_level = ContentFilterLevel(data.get("explicit_content_filter", 0))

        self.member_count = data.get("member_count", 0)

        # Create all the Role objects for the server.
        for role_data in data.get("roles", []):
            role_obj = dt_role.Role(self._bot, **role_data)
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
            channel_obj = dt_channel.Channel(self._bot, **channel_data)
            self._channels[channel_obj.id] = channel_obj
            channel_obj.guild_id = self.id
            channel_obj._update_overwrites(channel_data.get("permission_overwrites", []), )

        # Create all of the voice states.
        for vs_data in data.get("voice_states", []):
            user_id = int(vs_data.get("user_id", 0))
            member = self.members.get(user_id)
            if not member:
                # o well
                continue

            voice_state = dt_vs.VoiceState(**vs_data, client=self._bot)
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
    def invites(self) -> 'typing.AsyncIterator[dt_invite.Invite]':
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
            return "https://cdn.discordapp.com/splashes/{}/{}.webp".format(self.id,
                                                                           self.splash_hash)

    # Guild methods.
    async def leave(self) -> None:
        """
        Leaves the guild.
        """
        await self._bot.http.leave_guild(self.id)

    # async def connect_to_voice(self, channel: 'dt_channel.Channel') -> 'voice_client.VoiceClient':
    #     """
    #     Connects to a voice channel in this guild.
    #
    #     :param channel: The :class:`.Channel` to connect to.
    #     :return: The :class:`VoiceClient` that was connected to this guild.
    #     """
    #     if voice_client is None:
    #         raise RuntimeError("Cannot connect to voice - voice support is not installed")
    #
    #     if channel.guild != self:
    #         raise CuriousError("Cannot use channel from a different guild")
    #
    #     if self.voice_client is not None and self.voice_client.open:
    #         raise CuriousError("Voice client already exists in this guild")
    #
    #     gw = self._bot._gateways[self.shard_id]
    #     self.voice_client = await voice_client.VoiceClient.create(self._bot, gw, channel)
    #     await self.voice_client.connect()
    #     return self.voice_client

    async def get_invites(self) -> 'typing.List[dt_invite.Invite]':
        """
        Gets the invites for this guild.
        :return: A list :class:`.Invite` objects.
        """
        invites = await self._bot.http.get_invites_for(self.id)
        invites = [dt_invite.Invite(self._bot, **i) for i in invites]

        try:
            invite = await self.get_vanity_invite()
            invites.insert(0, invite)
        except (CuriousError, HTTPException):
            pass

        return invites

    async def kick(self, victim: 'dt_member.Member'):
        """
        Kicks somebody from the guild.

        :param victim: The :class:`.Member` to kick.
        """
        if not self.me.guild_permissions.kick_members:
            raise PermissionsError("kick_members")

        if victim.guild != self:
            raise ValueError("Member must be from this guild (try `member.user` instead)")

        if victim.top_role >= self.me.top_role:
            raise HierarchyError("Top role is equal to or lower than victim's top role")

        victim_id = victim.user.id

        await self._bot.http.kick_member(self.id, victim_id)

    @deprecated(since="0.7.0", see_instead=GuildBanContainer.add, removal="0.9.0")
    async def ban(self, victim: 'typing.Union[dt_member.Member, dt_user.User]', *,
                  delete_message_days: int = 7) -> GuildBan:
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
        """
        return await self.bans.add(victim, delete_message_days=delete_message_days)

    @deprecated(since="0.7.0", see_instead=GuildBanContainer.remove, removal="0.9.0")
    async def unban(self, user: 'dt_user.User') -> None:
        """
        Unbans a user from this guild.
        Example for unbanning the first banned user:

        .. code:: python

            user = next(await guild.get_bans())
            await guild.unban(user)

        To unban an arbitrary user, use :meth:`.Client.get_user`.

        .. code:: python

            user = await client.get_user(66237334693085184)
            await guild.unban(user)

        .. note::

            This does not take :class:`.Member` objects, as members cannot be in a guild and
            banned from the guild.

        :param user: The :class:`.User` to forgive and unban.
        """
        return await self.bans.remove(user)

    async def get_webhooks(self) -> 'typing.List[dt_webhook.Webhook]':
        """
        Gets the webhooks for this guild.

        :return: A list of :class:`.Webhook` objects for the guild.
        """
        webhooks = await self._bot.http.get_webhooks_for_guild(self.id)
        obbs = []

        for webhook in webhooks:
            obbs.append(self._bot.state.make_webhook(webhook))

        return obbs

    async def delete_webhook(self, webhook: 'dt_webhook.Webhook'):
        """
        Deletes a webhook in this guild.

        :param webhook: The :class:`.Webhook` to delete.
        """
        if not self.me.guild_permissions.manage_webhooks:
            raise PermissionsError("manage_webhooks")

        await self._bot.http.delete_webhook(webhook.id)

    async def change_role_positions(self,
                                    roles: 'typing.Union[typing.Dict[dt_role.Role, int], '
                                           'typing.List[typing.Tuple[dt_role.Role, int]]]'):
        """
        Changes the positions of a mapping of roles.

        :param roles: A dict or iterable of two-item tuples of new roles that is in the format of \
            (role, position).
        """
        if not self.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        if isinstance(roles, dict):
            roles = roles.items()

        to_send = []
        for r, new_position in roles:
            if new_position >= self.me.top_role.position:
                raise HierarchyError("Cannot move role above our top role")

            to_send.append((str(r.id), new_position))

        to_send = [(str(r.id), new_position) for (r, new_position) in roles]
        await self._bot.http.edit_role_positions(to_send)

    async def change_voice_state(self, member: 'dt_member.Member', *,
                                 deaf: bool = None, mute: bool = None,
                                 channel: 'dt_channel.Channel' = None):
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
        await self._bot.http.edit_member_voice_state(self.id,
                                                     member.id,
                                                     deaf=deaf, mute=mute, channel_id=channel_id)
        return member.voice

    async def modify_guild(self, *, afk_channel: 'dt_channel.Channel' = None,
                           verification_level: VerificationLevel = None,
                           content_filter_level: ContentFilterLevel = None,
                           notification_level: NotificationLevel = None,
                           **kwargs):
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
        await self._bot.http.edit_guild(self.id,
                                        icon_content=image)

    async def upload_icon(self, path: PathLike):
        """
        Uploads a new icon for the guild.

        :param path: A path-like object to use to upload.
        """
        with open(path, 'rb') as f:
            return await self.change_icon(f.read())

    async def get_widget_info(self) -> 'typing.Tuple[bool, ' \
                                       'typing.Union[None, dt_channel.Channel]]':
        """
        Gets the widget info for the current guild.
        
        :return: A two-item tuple: If this widget is enabled, and the channel the widget has an \ 
            invite for. 
        """
        info = await self._bot.http.get_widget_status(self.id)
        return info.get("enabled", False), self.channels.get(int(info.get("channel_id", 0)))

    async def edit_widget(self, *,
                          status: bool = None, channel: 'dt_channel.Channel' = -1):
        """
        Edits the widget for this guild.
        
        :param status: The status of this widget: True or False.
        :param channel: The channel object to set the instant invite to.
        """
        if channel is None:
            channel_id = None
        elif channel == -1:
            channel_id = 0
        else:
            channel_id = channel.id

        await self._bot.http.edit_widget(self.id, enabled=status, channel_id=channel_id)

    async def get_vanity_invite(self) -> 'typing.Union[None, dt_invite.Invite]':
        """
        Gets the vanity :class:`.Invite` for this guild.

        :return: The :class:`.Invite` that corresponds with this guild, if it has one.
        """
        if 'vanity-url' not in self.features:
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
        invite = dt_invite.Invite(self._bot, **invite_data)

        return invite

    async def set_vanity_invite(self, url: str) -> 'typing.Union[dt_invite.Invite, None]':
        """
        Sets the vanity :class:`.Invite` for this guild.

        :param url: The code to use for this guild.
        :return: The :class:`.Invite` produced.
        """
        if 'vanity-url' not in self.features:
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
        invite = dt_invite.Invite(self._bot, **invite_data)

        return invite
