from curious import client
from curious.dataclasses.bases import Dataclass
from curious.dataclasses import channel as dt_channel
from curious.dataclasses import message as dt_message
from curious.dataclasses import guild as dt_guild
from curious.exc import CuriousError


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
        return "<User id={} name={} discrim={}>".format(self.id, self.name, self.discriminator)

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

