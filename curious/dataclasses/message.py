import typing
import re

import curio

from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel
from curious.dataclasses import member as dt_member
from curious.dataclasses import role as dt_role
from curious.dataclasses import user as dt_user
from curious.util import to_datetime

CHANNEL_REGEX = re.compile(r"<#([0-9]*)>")


class Message(Dataclass):
    """
    Represents a Message.

    :ivar content: The content of this message.
    :ivar guild: The :class:`curious.dataclasses.guild.Guild` object that this message was sent in.
    :ivar channel: The :class:`curious.dataclasses.channel.Channel` object that this message was sent in.
    :ivar author: The :class:`curious.dataclasses.member.Member` object that this message belongs to.
        This could also be a :class:`curious.dataclasses.user.User` if the channel is private.
    :ivar created_at: A :class:`datetime.datetime` representing when this message was created.
    :ivar edited_at: A :class:`datetime.datetime` representing when this message was edited.
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
    def role_mentions(self) -> 'typing.List[dt_role.Role]':
        return self._resolve_mentions(self._role_mentions, "role")

    @property
    def channel_mentions(self):
        mentions = CHANNEL_REGEX.findall(self.content)
        return self._resolve_mentions(mentions, "channel")

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

    # Message methods
    async def delete(self):
        """
        Deletes this message.

        You must have MANAGE_MESSAGE permissions to delete this message, or have it be your own message.
        """
        await self._bot.http.delete_message(self.channel.id, self.id)

    async def edit(self, new_content: str, *,
                   wait: bool=False) -> 'Message':
        """
        Edits this message.

        You must be the owner of this message to edit it.
        This does NOT edit the message in place. Use `wait=True` to return the new, edited message object.

        :param new_content: The new content for this message.
        :param wait: Should we wait for a new message object to be created?
        :return: This message, but edited with the new content.
        """
        coro = self._bot.http.edit_message(self.channel.id, self.id, new_content=new_content)
        if wait:
            event = curio.Event()
            msg = None
            async def _listener(client, old_message, new_message: Message):
                if new_message.id == self.id:
                    await event.set()
                    # hacky use of nonlocal
                    nonlocal msg
                    msg = new_message
                    return True

            self._bot.add_listener("message_edit", _listener)

            message_data = await coro

            await event.wait()
            return msg
        else:
            message_data = await coro

    async def pin(self):
        """
        Pins this message.

        You must have MANAGE_MESSAGES in the channel to pin the message.
        """
        await self._bot.http.pin_message(self.channel.id, self.id)

    async def unpin(self):
        """
        Unpins this message.

        You must have MANAGE_MESSAGES in this channel to unpin the message.
        Additionally, the message must already be pinned.
        """
        await self._bot.http.unpin_message(self.channel.id, self.id)
