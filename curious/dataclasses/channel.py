import enum

from curious.dataclasses import guild as dt_guild
from curious.dataclasses.bases import Dataclass

from curious.dataclasses import message as dt_message
from curious.dataclasses.user import User


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

        #: Is this channel a private channel?
        self.is_private = kwargs.pop("is_private", False)

        #: If it is private, the recipient of the channel.
        if self.is_private:
            self.recipient = User(**kwargs.pop("user"))
        else:
            self.recipient = None

        #: The position of this channel.
        self.position = kwargs.pop("position", 0)

        #: The type of channel this channel is.
        self.type = ChannelType(kwargs.pop("type", 0))

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
