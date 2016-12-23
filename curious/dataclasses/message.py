import typing

from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel
from curious.dataclasses import member as dt_member
from curious.dataclasses import role as dt_role
from curious.dataclasses import user as dt_user
from curious.util import to_datetime


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

        #: The true timestamp of this message.
        #: This is not the snowflake timestamp.
        self.created_at = to_datetime(kwargs.pop("timestamp", None))

        #: The edited timestamp of this message.
        #: This can sometimes be None.
        edited_timestamp = kwargs.pop("edited_timestamp", None)
        if edited_timestamp is not None:
            self.edited_at = to_datetime(edited_timestamp)
        else:
            self.edited_at = None

        #: The mentions for this message.
        #: This is UNORDERED.
        self._mentions = kwargs.pop("mentions", [])

        #: The role mentions for this array.
        #: This is UNORDERED.
        self._role_mentions = kwargs.pop("mention_roles", [])

    @property
    def mentions(self):
        return self._resolve_mentions(self._mentions, "member")

    @property
    def role_mentions(self) -> typing.List['dt_role.Role']:
        return self._resolve_mentions(self._role_mentions, "role")

    def _resolve_mentions(self, mentions, type_: str) -> typing.List[Dataclass]:
        final_mentions = []
        for mention in mentions:
            if type_ == "member":
                id = int(mention["id"])
                obb = self.guild.get_member(id)
                if obb is None:
                    obb = dt_user.User(**mention)
            elif type_ == "role":
                obb = self.guild.get_role(int(mention))
            elif type_ == "channel":
                obb = self.guild.get_channel(int(mention))
            if obb is not None:
                final_mentions.append(obb)

        return final_mentions
