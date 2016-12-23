from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel
from curious.dataclasses import member as dt_member


class Message(Dataclass):
    """
    Represents a Message.
    """
    def __init__(self, client, **kwargs):
        super().__init__(kwargs.pop("id"), client)

        #: The content of the message.
        self.content = kwargs.pop("content", None)  # type: str

        #: The guild this message was sent in.
        #: This can be None if the message was sent in a DM.
        self.guild = None  # type: dt_guild.Guild

        #: The channel this message was sent in.
        self.channel = None  # type: dt_channel.Channel

        #: The author of this message.
        self.author = None  # type: dt_member.Member
