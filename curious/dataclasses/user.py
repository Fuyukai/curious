import enum
import typing
from collections import namedtuple
from types import MappingProxyType

from curious.dataclasses import channel as dt_channel, guild as dt_guild, message as dt_message
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.status import Game
from curious.dataclasses.status import Status
from curious.exc import CuriousError


class FriendType(enum.IntEnum):
    FRIEND = 1
    BLOCKED = 2

    INCOMING = 3
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

        #: Is this user premium?
        self.premium = kwargs.get("premium", False)

        #: When was this user premium since?
        self.premium_since = kwargs.get("premium_since", None)

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
        super().__init__(kwargs.pop("id"), client)

        #: The username of this user.
        self.username = kwargs.pop("username", None)

        #: The discriminator of this user.
        #: Note: This is a string, not an integer.
        self.discriminator = kwargs.pop("discriminator", None)

        #: The avatar hash of this user.
        self._avatar_hash = kwargs.pop("avatar", None)

        #: If this user is verified or not.
        self.verified = kwargs.pop("verified", None)

        #: If this user has MFA enabled or not.
        self.mfa_enabled = kwargs.pop("mfa_enabled", None)

        #: If this user is a bot.
        self.bot = kwargs.pop("bot", False)

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
        """
        if self.discriminator == "0000":
            raise CuriousError("Cannot open a private channel with a webhook")

        # First, try and access the channel from the channel cache.
        original_channel = self._bot.state._get_channel(self.id)
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
        :return: A :class:`UserProfile` representing this user's profile.
        """
        if self._bot.user.bot:
            raise CuriousError("Bots cannot get profiles")

        profile = await self._bot.http.get_user_profile(self.id)
        return UserProfile(user=self, kwargs=profile)

    async def send(self, content: str = None, *args, **kwargs) -> 'dt_message.Message':
        """
        Sends a message to the user over a private channel.

        :param content: The contet of the message to send.
        :return: A new :class:`Message` representing the sent message.
        """
        channel = await self.open_private_channel()
        message = await channel.send(content, *args, **kwargs)

        return message

    def unban_from(self, guild: 'dt_guild.Guild'):
        """
        Unbans this user from a guild.

        :param guild: The guild to unban in.
        """
        return guild.unban(self)


class BotUser(User):
    """
    A special type of user that represents ourselves.
    """
    __slots__ = ()

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

    @property
    def friends(self) -> typing.Mapping[int, 'RelationshipUser']:
        """
        :return: A mapping of :class:`FriendUser` that represents the friends for this user.
        """
        if self.bot:
            raise CuriousError("Bots cannot have friends")

        return MappingProxyType(self._bot.state._friends)

    @property
    def blocks(self) -> typing.Mapping[int, 'RelationshipUser']:
        """
        :return: A mapping of :class:`FriendUser` that represents the blocked users for this user.
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

        #: The type of friend this user is.
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
