import enum

from curious.dataclasses import guild as dt_guild
from curious.dataclasses.bases import Dataclass

from curious.dataclasses import message as dt_message
from curious.dataclasses import user as dt_user


class ChannelType(enum.Enum):
    TEXT = 0
    PRIVATE = 1
    VOICE = 2


class Channel(Dataclass):
    """
    Represents a channel.
    """

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.pop("id"), client)

        #: The name of this channel.
        self.name = kwargs.pop("name", None)

        #: The topic of this channel.
        self.topic = kwargs.pop("topic", None)

        #: The guild this channel is associated with.
        #: This can sometimes be None, if this channel is a private channel.
        self.guild = None  # type: dt_guild.Guild

        #: The type of channel this channel is.
        self.type = ChannelType(kwargs.pop("type", 0))

        #: Is this channel a private channel?
        self.is_private = kwargs.pop("is_private", self.type not in [ChannelType.TEXT, ChannelType.VOICE])

        #: If it is private, the recipients of the channel.
        self.recipients = []
        if self.is_private:
            for recipient in kwargs.pop("recipients"):
                self.recipients.append(dt_user.User(self._bot, **recipient))

        #: The position of this channel.
        self.position = kwargs.pop("position", 0)

    @property
    def user(self):
        """
        :return: If this channel is a private channel, return the user of the channel.
        """
        if self.type != ChannelType.PRIVATE:
            return None

        return self.recipients[0]

    async def send(self, content: str, *,
                   tts: bool = False) -> 'dt_message.Message':
        """
        Sends a message to this channel.

        :param content: The content of the message to send.
        :param tts: Should this message be text to speech?
        :return: A new :class:`Message` object.
        """
        if not isinstance(content, str):
            content = str(content)

        data = await self._bot.http.send_message(self.id, content)
        obb = self._bot.state.parse_message(data)

        return obb
