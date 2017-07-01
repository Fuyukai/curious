"""
Wrappers for Guild objects.

.. currentmodule:: curious.dataclasses.guild
"""
import collections
import datetime
import enum
import typing
import weakref
from math import ceil
from types import MappingProxyType

import curio

from curious.dataclasses import channel, emoji as dt_emoji, invite as dt_invite, \
    member as dt_member, permissions as dt_permissions, role, search as dt_search, user as dt_user, \
    voice_state as dt_vs, webhook as dt_webhook
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.presence import Presence, Status
from curious.exc import CuriousError, HTTPException, HierarchyError, PermissionsError
from curious.util import AsyncIteratorWrapper, base64ify

try:
    from curious.voice import voice_client
except ImportError:
    voice_client = None


class MFALevel(enum.IntEnum):
    """
    Represents the MFA level of a :class:`~.Guild`.
    """
    #: Used when MFA authentication is **disabled**.
    #: This means moderation actions will not require multi-factor auth.
    DISABLED = 0

    #: Used when MFA authentication is **enabled**.
    #: This means moderation actions *will* require multi-factor auth.
    ENABLED = 1


class VerificationLevel(enum.IntEnum):
    """
    Represents the verification levels for a :class:`~.Guild`.
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
        Checks if a :class:`~.Member` can speak in their :class:`~.Guild`.
        
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
    Represents the default notification level for a :class:`~.Guild`.
    """
    #: All messages notify members, by default.
    ALL_MESSAGES = 0

    #: Only mentions notify members, by default.
    ONLY_MENTIONS = 1


class ContentFilterLevel(enum.IntEnum):
    """
    Represents the content filter level for a :class:`~.Guild`. 
    """
    #: No messages will be scanned.
    SCAN_NONE = 0

    #: Messages from users without roles will be scanned.
    SCAN_WITHOUT_ROLES = 1

    #: All messages will be scanned.
    SCAN_ALL = 2


class GuildChannelWrapper(collections.Mapping, collections.Iterable):
    """
    A wrapper for channels on a guild. This provides some convenience methods which make channel
    management more fluent.
    """

    def __init__(self, guild: 'Guild',
                 channels: 'typing.MutableMapping[int, channel.Channel]'):
        """
        :param guild: The :class:`~.Guild` object that owns this wrapper.
        :param channels: The dictionary of channels that this wrapper contains.
        """
        self._guild = guild
        self._channels = channels

    @property
    def view(self) -> 'typing.Mapping[int, channel.Channel]':
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._channels)

    def __iter__(self):
        return iter(self.view.keys())

    def __getitem__(self, key):
        return self._channels[key]

    def __len__(self):
        return len(self._channels)

    def __repr__(self):
        return "<GuildChannelWrapper channels={}>".format(self._channels)

    async def create(self, name: str, type: 'channel.ChannelType',
                     permission_overwrites: 'typing.List[dt_permissions.Overwrite]' = None,
                     *,
                     bitrate: int = 64, user_limit: int = 0,
                     topic: str = None) -> 'channel.Channel':
        """
        Creates a new channel.

        :param name: The name of the channel.
        :param type: The :class:`.ChannelType` of the channel.
        :param permission_overwrites: The list of permission overwrites to use for this channel.

        For voice channels:

        :param bitrate: The bitrate of the channel, if it is a voice channel.
        :param user_limit: The maximum number of users that can be in the channel.

        For text channels:

        :param topic: The topic of the channel, or None to set no topic.
        """
        if not self._guild.me.guild_permissions.manage_channels:
            raise PermissionsError("manage_channels")

        kwargs = {
            "name": name,
            "type": type.value,
            "permission_overwrites": permission_overwrites,
        }
        if type is channel.ChannelType.VOICE:
            kwargs["bitrate"] = bitrate
            kwargs["user_limit"] = user_limit

        # create a listener so we wait for the WS before editing
        async def _listener(channel: channel.Channel):
            if channel.name == name and channel.guild == self._guild:
                return True

            return False

        listener = await curio.spawn(self._guild._bot.wait_for("member_update", _listener))
        try:
            channel_data = await self._guild._bot.http.create_channel(self._guild.id, **kwargs)
            # if it's a text channel and the topic was provided, automatically add it
            if type is channel.ChannelType.TEXT and topic is not None:
                await self._guild._bot.http.edit_channel(channel_id=channel_data["id"], topic=topic)
        except:
            await listener.cancel()
            raise

        # wait on the listener
        await listener.wait()
        # we can safely assume this exists
        return self._channels[int(channel_data.get("id"))]

    def edit(self, channel: 'channel.Channel', **kwargs):
        """
        Edits a channel.
        """
        if channel.id not in self._channels:
            raise CuriousError("This channel is not part of this guild")

        return channel.edit(**kwargs)

    def delete(self, channel: 'channel.Channel'):
        """
        Deletes a channel.
        """
        if channel.id not in self._channels:
            raise CuriousError("This channel is not part of this guild")

        return channel.delete()


class GuildRoleWrapper(collections.Mapping, collections.Iterable):
    """
    A wrapper for roles on a guild. Contains some convenience methods that make role management
    more fluent.
    """

    def __init__(self, guild: 'Guild',
                 roles: 'typing.MutableMapping[int, role.Role]'):
        """
        :param guild: The :class:`~.Guild` object that owns this wrapper.
        :param roles: The dictionary of roles that this wrapper contains.
        """
        self._guild = guild
        self._roles = roles

    @property
    def view(self) -> 'typing.Mapping[int, role.Role]':
        """
        :return: A read-only view into the channels for this wrapper.
        """
        return MappingProxyType(self._roles)

    def __iter__(self):
        return iter(self.view.keys())

    def __getitem__(self, key):
        return self._roles[key]

    def __len__(self):
        return len(self._roles)

    def __repr__(self):
        return "<GuildRoleWrapper roles={}>".format(self._roles)

    async def create(self, **kwargs) -> 'role.Role':
        """
        Creates a new role in this guild.

        :return: A new :class:`~.Role`.
        """
        if not self._guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        role_obb = role.Role(client=self._guild._bot,
                             **(await self._guild._bot.http.create_role(self._guild.id)))
        self._roles[role_obb.id] = role_obb
        role_obb.guild_id = self._guild.id
        return await role_obb.edit(**kwargs)

    def edit(self, role: 'role.Role', **kwargs):
        """
        Edits a role.
        """
        if role.id not in self._roles:
            raise CuriousError("This role is not part of this guild")

        return role.edit(**kwargs)

    def delete(self, role: 'role.Role'):
        """
        Deletes a role.
        """
        if role.id not in self._roles:
            raise CuriousError("This role is not part of this guild")

        return role.delete()


class Guild(Dataclass):
    """
    Represents a guild object on Discord.
    """

    __slots__ = (
        "id", "unavailable", "name", "afk_timeout", "region",
        "mfa_level", "verification_level", "notification_level", "content_filter_level", "features",
        "shard_id", "_roles", "_members", "_channels", "_emojis", "member_count",
        "_large", "_chunks_left", "_finished_chunking", "_icon_hash", "_splash_hash", "_owner_id",
        "_afk_channel_id", "voice_client",
        "channels", "roles"
    )

    def __init__(self, bot, **kwargs):
        """
        Creates a new Guild object.
        """
        super().__init__(kwargs.get("id"), bot)

        #: If the guild is unavailable or not.
        #: If this is True, many fields return `None`.
        self.unavailable = kwargs.get("unavailable", False)

        # Placeholder values.
        #: The name of this guild.
        self.name = None  # type: str
        #: The icon hash of this guild.
        #: Used to construct the icon URL later.
        self._icon_hash = None  # type: str
        #: The splash hash of this guild.
        #: Used to construct the splash URL later.
        self._splash_hash = None  # type: str

        #: The owner ID of this guild.
        self._owner_id = None  # type: int

        #: The AFK channel ID of this guild.
        self._afk_channel_id = None  # type: int
        #: The AFK timeout for this guild.
        self.afk_timeout = None  # type: int

        #: The voice region of this guild.
        self.region = None  # type: str

        #: The features this guild has.
        self.features = None  # type: typing.List[str]

        #: The MFA level of this guild.
        self.mfa_level = MFALevel.DISABLED  # type: MFALevel
        #: The verification level of this guild.
        self.verification_level = VerificationLevel.NONE  # type: int
        #: The notification level of this guild.
        self.notification_level = NotificationLevel.ALL_MESSAGES
        #: The content filter level of this guild.
        self.content_filter_level = ContentFilterLevel.SCAN_NONE

        #: The shard ID this guild is associated with.
        self.shard_id = None

        #: The roles that this guild has.
        self._roles = {}
        #: The members of this guild.
        self._members = {}
        #: The channels of this guild.
        self._channels = {}
        #: The emojis that this guild has.
        self._emojis = {}

        #: The number of numbers this guild has.
        #: This is automatically updated.
        self.member_count = 0  # type: int

        #: Is this guild a large guild?
        self._large = None  # type: bool

        #: Has this guild finished chunking?
        self._finished_chunking = curio.Event()
        self._chunks_left = 0

        #: The current voice client associated with this guild.
        self.voice_client = None  # type: VoiceClient

        #: The :class:`.GuildChannelWrapper` that wraps the channels in this Guild.
        self.channels = GuildChannelWrapper(self, self._channels)
        #: The :class:`.GuildRoleWrapper` that wraps the roles in this Guild.
        self.roles = GuildRoleWrapper(self, self._roles)

        if kwargs:
            self.from_guild_create(**kwargs)

    def _copy(self):
        obb = object.__new__(self.__class__)

        obb.unavailable = self.unavailable
        obb.name = self.name
        obb._icon_hash = self._icon_hash
        obb._splash_hash = self._splash_hash
        obb._owner_id = self._owner_id
        obb.region = self.region
        obb.shard_id = self.shard_id
        obb._roles = self._roles.copy()
        obb._members = self._members.copy()
        obb._channels = self._members.copy()
        obb.member_count = self.member_count
        obb._large = self._large
        obb._afk_channel_id = self._afk_channel_id
        obb.afk_timeout = self.afk_timeout
        obb.mfa_level = self.mfa_level
        obb._emojis = self._emojis.copy()
        obb.features = self.features

        return obb

    def __repr__(self):
        return "<Guild id='{}' name='{}' members='{}'>".format(self.id, self.name,
                                                               self.member_count)

    def __str__(self):
        return repr(self)

    @property
    def members(self) -> 'typing.Mapping[int, dt_member.Member]':
        """
        :return: A mapping of :class:`~.Member` that represent members on this guild.
        """
        return MappingProxyType(self._members)

    @property
    def emojis(self) -> 'typing.Mapping[int, dt_emoji.Emoji]':
        """
        :return: A mapping of :class:`~.Emoji` on this guild.
        """
        return MappingProxyType(self._emojis)

    @property
    def owner(self) -> 'dt_member.Member':
        """
        :return: A :class:`~.Member` object that represents the owner of this guild.
        """
        return self._members[self._owner_id]

    @property
    def me(self) -> 'typing.Union[dt_member.Member, None]':
        """
        :return: A :class:`~.Member` object that represents the current user in this guild.
        """
        try:
            return self._members[self._bot.user.id]
        except KeyError:
            return None

    @property
    def default_channel(self) -> 'typing.Union[channel.Channel, None]':
        """
        :return: A :class:`~.Channel` that represents the default channel of this guild.
        """
        try:
            return self._channels[self.id]
        except KeyError:
            return None

    @property
    def default_role(self) -> 'typing.Union[role.Role, None]':
        """
        :return: A :class:`~.Role` that represents the default role of this guild.
        """
        try:
            return self._roles[self.id]
        except KeyError:
            return None

    @property
    def afk_channel(self) -> 'typing.Union[None, channel.Channel]':
        """
        :return: A :class:`~.Channel` representing the AFK channel for this guild.
        """
        try:
            return self._channels[self._afk_channel_id]
        except IndexError:
            # the afk channel CAN be None
            return None

    @property
    def embed_url(self) -> str:
        """
        Gets the default embed url for this guild.
        If the widget is not enabled, this endpoint will 404.
        
        :return: The embed URL for this guild. 
        """
        return (self._bot.http.GUILD_BASE + "/embed.png").format(guild_id=self.id)

    # for parity with inviteguild
    @property
    def presence_count(self) -> int:
        """
        :return: The number of members with a non-Invisible presence. 
        """
        return sum(1 for member in self._members.values() if member.status is not Status.OFFLINE)

    # Presence methods
    def members_with_status(self,
                            status: Status) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        A generator that returns the members that match the specified status.
        """
        for member in self.members.values():
            if member.status == status:
                yield member

    @property
    def online_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of online :class:`~.Member` objects.
        """
        return self.members_with_status(Status.ONLINE)

    @property
    def idle_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of idle :class:`~.Member` objects.
        """
        return self.members_with_status(Status.IDLE)

    @property
    def dnd_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of DnD :class:`~.Member` objects.
        """
        return self.members_with_status(Status.DND)

    @property
    def offline_members(self) -> 'typing.Generator[dt_member.Member, None, None]':
        """
        :return: A generator of offline/invisible :class:`~.Member` objects.
        """
        return self.members_with_status(Status.OFFLINE)

    @property
    def search(self) -> 'dt_search.SearchQuery':
        """
        :return: A :class:`~.SearchQuery` that can be used to search this guild's messages. 
        """
        return dt_search.SearchQuery(guild=self)

    def get_embed_url(self, *, style: str = "banner1") -> str:
        """
        Gets an embed URL for this guild in a specified style.
        
        :param style: The style to get. 
        :return: The embed URL for this guild.
        """
        valid_styles = ('banner1', 'banner3', 'banner2', 'shield', 'banner4')
        if style not in valid_styles:
            raise ValueError("Style must be in {}".format(valid_styles))

        return self.embed_url + "?style={}".format(style)

    def find_member(self, search_str: str) -> 'dt_member.Member':
        """
        Attempts to find a member in this guild by name#discrim.
        This will also search nicknames.

        The discriminator is optional, but if provided allows better matching.

        :param search_str: The name#discrim pair to search for.
        :return: A :class:`~.Member` object that represents the member, or None if no member could \ 
            be found.
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
        try:
            return next(filtered)
        except StopIteration:
            return None

    # creation methods
    def start_chunking(self):
        """
        Marks a guild to start guild chunking.
        
        This will clear the chunking event, and calculate the number of member chunks required.
        """
        self._finished_chunking.clear()
        self._chunks_left = ceil(self.member_count / 1000)

    async def wait_until_chunked(self):
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
            id = int(member_data["user"]["id"])
            if id in self._members:
                member_obj = self._members[id]
            else:
                member_obj = dt_member.Member(self._bot, **member_data)

            member_obj.nickname = member_data.get("nick", member_obj.nickname)
            member_obj.guild_id = self.id

            self._members[member_obj.id] = member_obj

    def _handle_emojis(self, emojis: list):
        """
        Handles the emojis for this guild.
        
        :param emojis: A list of emoji objects from Discord.
        """
        for emoji in emojis:
            emoji_obj = dt_emoji.Emoji(**emoji)
            emoji_obj.guild = self
            for role_id in emoji_obj._role_ids:
                emoji_obj.roles.append(self._roles.get(int(role_id)))

            self._emojis[emoji_obj.id] = emoji_obj

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
        self._icon_hash = data.get("icon")  # type: str
        self._splash_hash = data.get("splash")  # type: str
        self._owner_id = int(data.get("owner_id"))  # type: int
        self._large = data.get("large", None)
        self.features = data.get("features", [])
        self.region = data.get("region")
        afk_channel_id = data.get("afk_channel_id")
        if afk_channel_id is not None:
            afk_channel_id = int(afk_channel_id)
        self._afk_channel_id = afk_channel_id
        self.afk_timeout = data.get("afk_timeout")

        self.verification_level = VerificationLevel(data.get("verification_level", 0))
        self.mfa_level = MFALevel(data.get("mfa_level", 0))
        self.notification_level = NotificationLevel(data.get("default_message_notifications"))
        self.content_filter_level = ContentFilterLevel(data.get("explicit_content_filter", 0))

        self.member_count = data.get("member_count", 0)

        # Create all the Role objects for the server.
        for role_data in data.get("roles", []):
            role_obj = role.Role(self._bot, **role_data)
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
            channel_obj = channel.Channel(self._bot, **channel_data)
            channel_obj.guild_id = self.id
            channel_obj._update_overwrites(channel_data.get("permission_overwrites", []),
                                           guild=self)
            self._channels[channel_obj.id] = channel_obj

        # Create all of the voice states.
        for vs_data in data.get("voice_states", []):
            user_id = int(vs_data.get("user_id", 0))
            member = self.members.get(user_id)
            if not member:
                # o well
                continue

            voice_state = dt_vs.VoiceState(**vs_data)

            vs_channel = self._channels.get(int(vs_data.get("channel_id", 0)))
            if vs_channel is not None:
                voice_state._channel_id = vs_channel.id
                voice_state._guild_id = self.id

                voice_state._guild = weakref.ref(self)
                voice_state._channel = weakref.ref(vs_channel)

            member.voice = voice_state

        # Create all of the emoji objects for the server.
        self._handle_emojis(data.get("emojis", []))

    @property
    def large(self) -> bool:
        """
        :return: If this guild is large or not (>= 250 members).
        """
        if self._large is not None:
            return self._large

        return self.member_count >= self._bot.gateways[self.shard_id].large_threshold

    @property
    def bans(self) -> 'typing.AsyncIterator[dt_user.User]':
        """
        :return: A :class:`~.AsyncIteratorWrapper` that yields :class:`~.User` objects that are banned.
        """
        return AsyncIteratorWrapper(self.get_bans())

    @property
    def invites(self) -> 'typing.AsyncIterator[dt_invite.Invite]':
        """
        :return: A class:`~.AsyncIteratorWrapper` that yields :class:`~.Invite` objects for this guild. 
        """
        return AsyncIteratorWrapper(self.get_invites())

    @property
    def icon_url(self) -> str:
        """
        :return: The icon URL for this guild, or None if one isn't set.
        """
        if self._icon_hash:
            return "https://cdn.discordapp.com/icons/{}/{}.webp".format(self.id, self._icon_hash)

    @property
    def splash_url(self) -> str:
        """
        :return: The splash URL for this guild, or None if one isn't set.
        """
        if self._splash_hash:
            return "https://cdn.discordapp.com/splashes/{}/{}.webp".format(self.id,
                                                                           self._splash_hash)

    # Guild methods.
    async def leave(self):
        """
        Leaves the guild.
        """
        await self._bot.http.leave_guild(self.id)

    async def connect_to_voice(self, channel: 'channel.Channel') -> 'voice_client.VoiceClient':
        """
        Connects to a voice channel in this guild.

        :param channel: The :class:`~.Channel` to connect to.
        :return: The :class:`VoiceClient` that was connected to this guild.
        """
        if voice_client is None:
            raise RuntimeError("Cannot to voice - voice support is not installed")

        VoiceClient = voice_client.VoiceClient

        if channel.guild != self:
            raise CuriousError("Cannot use channel from a different guild")

        if self.voice_client is not None and self.voice_client.open:
            raise CuriousError("Voice client already exists in this guild")

        gw = self._bot._gateways[self.shard_id]
        self.voice_client = await VoiceClient.create(self._bot, gw, channel)
        await self.voice_client.connect()
        return self.voice_client

    async def get_invites(self) -> 'typing.List[dt_invite.Invite]':
        """
        Gets the invites for this guild.
        :return: A list :class:`~.Invite` objects.
        """
        invites = await self._bot.http.get_invites_for(self.id)
        invites = [dt_invite.Invite(self._bot, **i) for i in invites]

        try:
            invite = await self.get_vanity_invite()
        except (CuriousError, HTTPException):
            pass
        else:
            if invite is not None:
                invites.append(invite)

        return invites

    async def get_bans(self) -> 'typing.List[dt_user.User]':
        """
        Gets the bans for this guild.
        :return: A list of User objects, one for each ban.
        """
        if not self.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        bans = await self._bot.http.get_bans(self.id)
        users = []

        for user_data in bans:
            # TODO: Audit log stuff, if it ever comes out.
            user_data = user_data.get("user", None)
            users.append(dt_user.User(self._bot, **user_data))

        return users

    async def kick(self, victim: 'dt_member.Member'):
        """
        Kicks somebody from the guild.

        :param victim: The :class:`~.Member` to kick.
        """
        if not self.me.guild_permissions.kick_members:
            raise PermissionsError("kick_members")

        if victim.guild != self:
            raise ValueError("Member must be from this guild (try `member.user` instead)")

        if victim.top_role >= self.me.top_role:
            raise HierarchyError("Top role is equal to or lower than victim's top role")

        victim_id = victim.user.id

        await self._bot.http.kick_member(self.id, victim_id)

    async def ban(self, victim: 'typing.Union[dt_member.Member, dt_user.User]', *,
                  delete_message_days: int = 7):
        """
        Bans somebody from the guild.

        This can either ban a :class:`~.Member`, in which they must be in the guild. 
        Or this can ban a :class:`~.User`, which does not need to be in the guild.

        Example for banning a member:

        .. code:: python

            member = guild.members[66237334693085184]
            await guild.ban(member)

        Example for banning a user:

        .. code:: python

            user = await client.get_user(66237334693085184)
            await guild.ban(user)

        :param victim: The :class:`~.Member` or :class:`~.User` object to ban.
        :param delete_message_days: The number of days to delete messages.
        """
        if not self.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        if isinstance(victim, dt_member.Member):
            if self.owner == victim:
                raise HierarchyError("Cannot ban the owner")

            if victim.guild != self:
                raise ValueError("Member must be from this guild (try `member.user` instead)")

            if victim.top_role >= self.me.top_role:
                raise HierarchyError("Top role is equal to or lower than victim's top role")

            victim_id = victim.user.id

        elif isinstance(victim, dt_user.User):
            victim_id = victim.id

        else:
            raise TypeError("Victim must be a Member or a User")

        await self._bot.http.ban_user(guild_id=self.id, user_id=victim_id,
                                      delete_message_days=delete_message_days)

    async def unban(self, user: 'dt_user.User'):
        """
        Unbans a user from this guild.

        Example for unbanning the first banned user:

        .. code:: python

            user = next(await guild.get_bans())
            await guild.unban(user)

        To unban an arbitrary user, use :meth:`~.Client.get_user`.

        .. code:: python

            user = await client.get_user(66237334693085184)
            await guild.unban(user)

        :param user: The :class:`~.User` to forgive and unban.
        """
        if not self.me.guild_permissions.ban_members:
            raise PermissionsError("ban_members")

        forgiven_id = user.id

        await self._bot.http.unban_user(self.id, forgiven_id)

    async def get_webhooks(self) -> 'typing.List[dt_webhook.Webhook]':
        """
        Gets the webhooks for this guild.

        :return: A list of :class:`~.Webhook` objects for the guild.
        """
        webhooks = await self._bot.http.get_webhooks_for_guild(self.id)
        obbs = []

        for webhook in webhooks:
            obbs.append(self._bot.state.make_webhook(webhook))

        return obbs

    async def delete_webhook(self, webhook: 'dt_webhook.Webhook'):
        """
        Deletes a webhook in this guild.

        :param webhook: The :class:`~.Webhook` to delete.
        """
        if not self.me.guild_permissions.manage_webhooks:
            raise PermissionsError("manage_webhooks")

        await self._bot.http.delete_webhook(webhook.id)

    async def add_roles(self, member: 'dt_member.Member', *roles: 'role.Role'):
        """
        Adds roles to a member.

        This will wait until the gateway returns the GUILD_MEMBER_UPDATE with the new role list 
        for the member before returning.

        .. code:: python

            roles = filter(lambda r: "Mod" in r.name, guild.roles)
            await guild.add_roles(member, *roles)

        :param member: The :class:`~.Member` to add roles to.
        :param roles: An iterable of :class:`~.Role` objects to add.
        """
        if not self.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        # Ensure we can add all of these roles.
        for _r in roles:
            if _r >= self.me.top_role:
                msg = "Cannot add role {} - it has a higher or equal position to our top role" \
                    .format(_r.name)
                raise HierarchyError(msg)

        async def _listener(before, after: dt_member.Member):
            if after.id != member.id:
                return False

            if not all(role in after.roles for role in roles):
                return False

            return True

        role_ids = set([_r.id for _r in member.roles] + [_r.id for _r in roles])
        listener = await curio.spawn(self._bot.wait_for("member_update", _listener))

        try:
            await self._bot.http.edit_member_roles(self.id, member.id, role_ids)
        except:
            await listener.cancel()
            raise

        # Now wait for the event to happen on the gateway.
        await listener.join()

        return member

    async def remove_roles(self, member: 'dt_member.Member', *roles: 'role.Role'):
        """
        Removes roles from a member.

        This will wait until the gateway fires a GUILD_MEMBER_UPDATE.

        :param member: The :class:`~.Member` to remove roles from.
        :param roles: An iterable of :class:`Role` to remove.
        """
        if not self.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        for _r in roles:
            if _r >= self.me.top_role:
                msg = "Cannot remove role {} - it has a higher or equal position to our top role" \
                    .format(_r.name)
                raise HierarchyError(msg)

        async def _listener(before, after: dt_member.Member):
            if after.id != member.id:
                return False

            if not all(role not in after.roles for role in roles):
                return False

            return True

        # Calculate the roles to keep.
        to_keep = set(member.roles) - set(roles)

        role_ids = set([_r.id for _r in to_keep])
        listener = await curio.spawn(self._bot.wait_for("member_update", _listener))

        try:
            await self._bot.http.edit_member_roles(self.id, member.id, role_ids)
        except:
            await listener.cancel()
            raise
        await listener.join()

        return member

    async def change_nickname(self, member: 'dt_member.Member', new_nickname: str):
        """
        Changes the nickname of a member.

        :param member: The :class:`~.Member` to change the nickname of.
        :param new_nickname: The new nickname.
        """
        me = False
        if member == self.me:
            me = True
            if not self.me.guild_permissions.change_nickname:
                raise PermissionsError("change_nickname")
        else:
            if not self.me.guild_permissions.manage_nicknames:
                raise PermissionsError("manage_nicknames")

        if member.top_role >= self.me.top_role and member != self.me:
            raise HierarchyError("Top role is equal to or lower than victim's top role")

        if new_nickname is not None and len(new_nickname) > 32:
            raise ValueError("Nicknames cannot be longer than 32 characters")

        coro = self._bot.http.change_nickname(self.id, new_nickname,
                                              member_id=member.id, me=me)

        async def _listener(before, after):
            return after.guild == self and after.id == member.id

        listener = await curio.spawn(
            self._bot.wait_for("member_update", _listener)
        )  # type: curio.Task

        try:
            await coro
        except:
            await listener.cancel()
            raise
        await listener.join()

        return member

    async def change_role_positions(self, roles: 'typing.Union[typing.Dict[role.Role, int], '
                                                 'typing.List[typing.Tuple[role.Role, int]]]'):
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
                                 deaf: bool = None, mute: bool = None):
        """
        Changes the voice state of a member.

        :param member: The :class:`~.Member` to change the voice state of.
        :param deaf: Should this member be deafened?
        :param mute: Should this member be muted?
        """
        if member.voice is None:
            raise CuriousError("Cannot change voice state of member not in voice")

        await self._bot.http.edit_member_voice_state(self.id, member.id, deaf=deaf, mute=mute)
        return member.voice

    async def modify_guild(self, *, afk_channel: 'channel.Channel' = None,
                           verification_level: VerificationLevel = None,
                           content_filter_level: ContentFilterLevel = None,
                           notification_level: NotificationLevel = None,
                           **kwargs):
        """
        Edits this guild.

        For a list of available arguments, see 
        https://discordapp.com/developers/docs/resources/guild#modify-guild.
        
        :param afk_channel: The :class:`~.Channel` that represents the AFK voice channel.
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

    def upload_icon(self, path):
        """
        Uploads a new icon for the guild.

        :param path: A path-like object to use to upload.
        """
        with open(path, 'rb') as f:
            return self.change_icon(f.read())

    async def get_widget_info(self) -> 'typing.Tuple[bool, typing.Union[None, channel.Channel]]':
        """
        Gets the widget info for the current guild.
        
        :return: A two-item tuple: If this widget is enabled, and the channel the widget has an \ 
            invite for. 
        """
        info = await self._bot.http.get_widget_status(self.id)
        return info.get("enabled", False), self.channels.get(int(info.get("channel_id", 0)))

    async def edit_widget(self, *,
                          status: bool = None, channel: 'channel.Channel' = -1):
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

    async def get_vanity_invite(self) -> 'dt_invite.Invite':
        """
        Gets the vanity :class:`~.Invite` for this guild.

        :return: The :class:`~.Invite` that corresponds with this guild.
        """
        if 'vanity-url' not in self.features:
            raise CuriousError("This guild has no vanity URL")

        try:
            resp = await self._bot.http.get_vanity_url(self.id)
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

    async def set_vanity_invite(self, url: str) -> 'dt_invite.Invite':
        """
        Sets the vanity :class:`~.Invite` for this guild.

        :param url: The code to use for this guild.
        :return: The :class:`~.Invite` produced.
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

    @property
    def recent_mentions(self):
        """
        :return: A :class:`~.AsyncIteratorWrapper` that can be used to get all the mentions for \ 
            this user in this guild.
        """
        return AsyncIteratorWrapper(
            self.get_recent_mentions(limit=100, everyone_mentions=True, role_mentions=True)
        )

    def get_recent_mentions(self, *,
                            limit: int = 25,
                            everyone_mentions: bool = True, role_mentions: bool = True):
        """
        Gets mentions in this guild.
        """
        if self.me.user.bot is True:
            raise CuriousError("Cannot get recent mentions on bot accounts")

        return self.me.user.get_recent_mentions(guild=self, limit=limit,
                                                everyone_mentions=everyone_mentions,
                                                role_mentions=role_mentions)
