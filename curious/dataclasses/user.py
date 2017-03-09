"""
Wrappers for User objects.

.. currentmodule:: curious.dataclasses.user
"""

import enum
import typing
from collections import namedtuple

from curious.util import attrdict
from types import MappingProxyType

from curious.dataclasses import channel as dt_channel, guild as dt_guild, message as dt_message
from curious.dataclasses.appinfo import AuthorizedApp, AppInfo
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.status import Game
from curious.dataclasses.status import Status
from curious.exc import CuriousError


class FriendType(enum.IntEnum):
    """
    Represents the type of a friend.
    """

    #: Corresponds to a friend.
    FRIEND = 1

    #: Corresponds to a blocked user.
    BLOCKED = 2

    #: Corresponds to an incoming friend request.
    INCOMING = 3

    #: Corresponds to an outgoing friend request.
    OUTGOING = 4


connection = namedtuple("Connection", "type id name")


class UserProfile(object):
    """
    Represents a profile for a user.
    """

    def __init__(self, user: 'User', kwargs):
        #: The user object associated with this profile.
        self.user = user

        #: A list of connections associated with this profile.
        self.connections = [connection(**c) for c in kwargs.get("connected_accounts", [])]

        #: When was this user premium since?
        self.premium_since = kwargs.get("premium_since", None)

    @property
    def premium(self) -> bool:
        """
        :return: ``True`` if this user has Nitro, ``False`` if not. 
        """
        return self.premium_since is not None

    def __repr__(self):
        return "<UserProfile user='{}' premium={}>".format(self.user, self.premium)


class User(Dataclass):
    """
    This represents a bare user - i.e, somebody without a guild attached.
    This is used in DMs and similar. All member objects have a reference to their user on ``.user``.

    :ivar id: The ID of this user.
    """

    __slots__ = ("username", "discriminator", "_avatar_hash", "verified", "mfa_enabled", "bot", "_bot")

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.get("id"), client)

        #: The username of this user.
        self.username = kwargs.get("username", None)

        #: The discriminator of this user.
        #: Note: This is a string, not an integer.
        self.discriminator = kwargs.get("discriminator", None)

        #: The avatar hash of this user.
        self._avatar_hash = kwargs.get("avatar", None)

        #: If this user is verified or not.
        self.verified = kwargs.get("verified", None)

        #: If this user has MFA enabled or not.
        self.mfa_enabled = kwargs.get("mfa_enabled", None)

        #: If this user is a bot.
        self.bot = kwargs.get("bot", False)

    def _copy(self):
        new_object = object.__new__(self.__class__)
        new_object.id = self.id
        new_object.username = self.username
        new_object.discriminator = self.discriminator
        new_object._avatar_hash = self._avatar_hash
        new_object.verified = self.verified
        new_object.mfa_enabled = self.mfa_enabled
        new_object.bot = self.bot

        new_object._bot = self._bot

        return new_object

    @property
    def avatar_url(self) -> str:
        """
        :return: The avatar URL of this user.
        """
        if not self._avatar_hash:
            return "https://cdn.discordapp.com/embed/avatars/{}.png".format(int(self.discriminator) % 5)

        # `a_` signifies Nitro and that they have an animated avatar.
        if self._avatar_hash.startswith("a_"):
            suffix = ".gif"  # soon: animated webp
        else:
            suffix = ".webp"

        return "https://cdn.discordapp.com/avatars/{}/{}{}".format(self.id, self._avatar_hash, suffix)

    @property
    def name(self):
        return self.username

    @property
    def mention(self):
        """
        :return: A string that mentions this user.
        """
        return "<@{}>".format(self.id)

    @property
    def created_at(self):
        """
        :return: The time this user was created.
        :rtype: datetime.datetime
        """
        return self.timestamp

    def __repr__(self):
        return "<{} id={} name={} discrim={}>".format(type(self).__name__, self.id, self.name, self.discriminator)

    def __str__(self):
        return "{}#{}".format(self.username, self.discriminator)

    async def open_private_channel(self) -> 'dt_channel.Channel':
        """
        Opens a private channel with a user.

        :return: The newly created private channel.
        :rtype: :class:`~.Channel`
        """
        if self.discriminator == "0000":
            raise CuriousError("Cannot open a private channel with a webhook")

        # First, try and access the channel from the channel cache.
        original_channel = self._bot.state.find_channel(self.id)
        if original_channel:
            return original_channel

        # Failing that, open a new private channel.
        channel_data = await self._bot.http.open_private_channel(self.id)
        channel = self._bot.state.make_private_channel(channel_data)
        return channel

    async def block(self):
        """
        Blocks this user.
        """
        if self._bot.is_bot:
            raise CuriousError("Bots cannot have blocks")

        await self._bot.http.block_user(self.id)

    async def send_friend_request(self):
        """
        Sends a friend request to this user.
        """
        if self._bot.is_bot:
            raise CuriousError("Bots cannot have friends")

        await self._bot.http.send_friend_request(self.id)

    async def get_profile(self) -> UserProfile:
        """
        :return: A :class:`~.UserProfile` representing this user's profile.
        """
        if self._bot.user.bot:
            raise CuriousError("Bots cannot get profiles")

        profile = await self._bot.http.get_user_profile(self.id)
        return UserProfile(user=self, kwargs=profile)

    async def send(self, content: str = None, *args, **kwargs) -> 'dt_message.Message':
        """
        Sends a message to the user over a private channel.

        :param content: The contet of the message to send.
        :return: A new :class:`~.Message` representing the sent message.
        """
        channel = await self.open_private_channel()
        message = await channel.send(content, *args, **kwargs)

        return message

    def unban_from(self, guild: 'dt_guild.Guild'):
        """
        Unbans this user from a guild.

        :param guild: The :class:`~.Guild` to unban in.
        """
        return guild.unban(self)


class UserSettings(attrdict):
    """
    Represents the settings for a user.
    """

    def __init__(self, client, **kwargs):
        self._bot = client

        #: Are emoticons converted automatically?
        #: For example, :) will turn into the emoji literal.
        self.convert_emoticons = kwargs.get("convert_emoticons", True)

        #: Are platform accounts detected?
        self.detect_platform_accounts = kwargs.get("detect_platform_accounts", True)

        #: Is developer mode enabled?
        self.developer_mode = kwargs.get("developer_mode", False)

        #: Is the TTS command enabled?
        self.enable_tts_command = kwargs.get("enable_tts_command", True)

        #: The guild positions for this user.
        self.guild_positions = kwargs.get("guild_positions", [])

        #: The friend source flags for this user.
        self.friend_source_flags = kwargs.get("friend_source_flags", {})

        #: Are inline attachments enabled?
        self.inline_attachment_media = kwargs.get("inline_attachment_media", True)

        #: Are inline embeds enabled?
        self.inline_embed_media = kwargs.get("inline_embed_media", True)

        #: The locale for this user.
        self.locale = kwargs.get("locale", 'en-US')

        #: Is compact mode enabled?
        self.message_display_compact = kwargs.get("message_display_compact", False)

        #: Render embeds?
        self.render_embeds = kwargs.get("render_embeds", True)

        #: Render reactions?
        self.render_reactions = kwargs.get("render_reactions", True)

        #: Restricted guilds (guilds you have DMs disabled for).
        self.restricted_guilds = kwargs.get("restricted_guilds", [])

        #: Show the current game?
        self.show_current_game = kwargs.get("show_current_game", True)

        #: The current theme for this user.
        self.theme = kwargs.get("theme", 'light')

    async def update(self, **kwargs):
        """
        Updates the current user's settings with the keyword args provided.
        
        This will PATCH to Discord, as well.
        """
        # copy a new set of settings and pass it straight to `http.update_user_settings`
        settings = self.copy()
        dict.update(settings, **kwargs)
        # remove this so discord dont get confused
        settings.pop("_bot")

        new_settings = await self._bot.http.update_user_settings(**settings)
        # update ourselves
        dict.update(self, **new_settings)

        return self


class BotUser(User):
    """
    A special type of user that represents ourselves.
    """

    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs)

        #: The email for this user.
        self.email = kwargs.get("email", None)

        #: Does this user use mobile?
        self.mobile = kwargs.get("mobile", False)

        #: Is this user premium?
        self.premium = kwargs.get("premium", False)

        #: The current :class:`~.UserSettings` for this user.
        self.settings = None  # type: UserSettings

    async def open_private_channel(self):
        raise NotImplementedError("Cannot open a private channel with yourself")

    async def send(self, *args, **kwargs):
        raise NotImplementedError("Cannot send messages to your own user")

    async def block(self, *args, **kwargs):
        raise NotImplementedError("Cannot block or unblock yourself")

    unblock = block

    async def send_friend_request(self):
        raise NotImplementedError("Cannot be friends with yourself")

    remove_friend = send_friend_request

    def edit(self, *args, **kwargs):
        """
        Edits the bot's current profile.
        """
        return self._bot.edit_profile(*args, **kwargs)

    def upload_avatar(self, path: str):
        """
        Edits the bot's current avatar.
        """
        return self._bot.edit_avatar(path)

    async def get_authorized_apps(self) -> typing.Sequence[AuthorizedApp]:
        """
        Gets a list of authorized applications for this user.
        :return: A sequence of :class:`~.AuthorizedApp`.
        """
        data = await self._bot.http.get_authorized_apps()
        final = []

        for item in data:
            id = int(item.get("id", 0))
            final.append(AuthorizedApp(id=id, scopes=item.get("scopes", []),
                                       application=AppInfo(self._bot, **item)))

        return final

    @property
    def friends(self) -> typing.Mapping[int, 'RelationshipUser']:
        """
        :return: A mapping of :class:`~.RelationshipUser` that represents the friends for this user.
        """
        if self.bot:
            raise CuriousError("Bots cannot have friends")

        return MappingProxyType(self._bot.state._friends)

    @property
    def blocks(self) -> typing.Mapping[int, 'RelationshipUser']:
        """
        :return: A mapping of :class:`~.RelationshipUser` that represents the blocked users for this user.
        """
        if self.bot:
            raise CuriousError("Bots cannot have friends")

        return MappingProxyType(self._bot.state._blocked)


class RelationshipUser(User):
    """
    A user that is either friends or blocked with the current user.
    
    Only useful for user bots.
    """

    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs)

        #: The status for this friend.
        self.status = None  # type: Status

        #: The game for this friend.
        self.game = None  # type: Game

        #: The :class:`.FriendType` of friend this user is.
        self.type_ = None  # type: FriendType

    async def remove_friend(self):
        """
        Removes this user as a friend.
        """
        if self._bot.is_bot:
            raise CuriousError("Bots cannot have friends")

        if self.type_ != FriendType.FRIEND:
            raise CuriousError("This user is not your friend")

        await self._bot.http.remove_relationship(self.id)

    async def unblock(self):
        """
        Unblocks this user.
        """
        if self._bot.is_bot:
            raise CuriousError("Bots cannot have blocks")

        if self.type_ != FriendType.BLOCKED:
            raise CuriousError("This user is not blocked")

        await self._bot.http.remove_relationship(self.id)
