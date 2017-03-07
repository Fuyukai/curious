"""
Wrappers for Message objects.

.. currentmodule:: curious.dataclasses.message
"""

import typing
import re

import curio

from curious.dataclasses.bases import Dataclass
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel
from curious.dataclasses import member as dt_member
from curious.dataclasses import role as dt_role
from curious.dataclasses import user as dt_user
from curious.dataclasses import webhook as dt_webhook
from curious.dataclasses.embed import Embed, Attachment
from curious.dataclasses import emoji as dt_emoji
from curious.exc import CuriousError, PermissionsError
from curious.util import to_datetime

CHANNEL_REGEX = re.compile(r"<#([0-9]*)>")


class Message(Dataclass):
    """
    Represents a Message.

    :ivar id: The ID of this message.
    """

    __slots__ = ("content", "guild", "author", "channel", "created_at", "edited_at", "embeds", "attachments",
                 "_mentions", "_role_mentions", "reactions", "channel_id", "author_id")

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.get("id"), client)

        #: The content of the message.
        self.content = kwargs.get("content", None)  # type: str

        #: The guild this message was sent in.
        #: This can be None if the message was sent in a DM.
        self.guild = None  # type: dt_guild.Guild

        #: The ID of the channel the message was sent in.
        self.channel_id = int(kwargs.get("channel_id", 0))  # type: int

        #: The :class:`~.Channel` this message was sent in.
        self.channel = None  # type: dt_channel.Channel

        #: The ID of the author.
        self.author_id = int(kwargs.get("author_id", 0))  # type: int

        #: The author of this message. Can be one of: :class:`.Member`, :class:`.Webhook`, :class:`.User`.
        self.author = None  # type: typing.Union[dt_member.Member, dt_webhook.Webhook]

        #: The true timestamp of this message.
        #: This is not the snowflake timestamp.
        self.created_at = to_datetime(kwargs.get("timestamp", None))

        #: The edited timestamp of this message.
        #: This can sometimes be None.
        edited_timestamp = kwargs.get("edited_timestamp", None)
        if edited_timestamp is not None:
            self.edited_at = to_datetime(edited_timestamp)
        else:
            self.edited_at = None

        #: The list of embeds this message contains.
        self.embeds = []
        for embed in kwargs.get("embeds", []):
            self.embeds.append(Embed(**embed))

        #: The list of attachments this message contains.
        self.attachments = []

        for attachment in kwargs.get("attachments", []):
            self.attachments.append(Attachment(**attachment))

        #: The mentions for this message.
        #: This is UNORDERED.
        self._mentions = kwargs.get("mentions", [])

        #: The role mentions for this message.
        #: This is UNORDERED.
        self._role_mentions = kwargs.get("mention_roles", [])

        #: The reactions for this message.
        self.reactions = []

    def __repr__(self):
        return "<{0.__class__.__name__} id={0.id} content='{0.content}'>".format(self)

    def __str__(self):
        return self.content

    @property
    def mentions(self) -> 'typing.List[dt_member.Member]':
        """
        Returns a list of :class:`~.Member` that were mentioned in this message. 
        
        .. warning::
            
            The mentions in this will **not** be in order. Discord does not return them in any paticular order.
        """
        return self._resolve_mentions(self._mentions, "member")

    @property
    def role_mentions(self) -> 'typing.List[dt_role.Role]':
        """
        Returns a list of :class:`~.Role` that were mentioned in this message.
        
        .. warning::
            
            The mentions in this will **not** be in order. Discord does not return them in any paticular order.
        """

        return self._resolve_mentions(self._role_mentions, "role")

    @property
    def channel_mentions(self):
        """
        Returns a list of :class:`~.Channel` that were mentioned in this message.
        
        .. note::
        
            These mentions **are** in order. They are parsed from the message content.
        """
        mentions = CHANNEL_REGEX.findall(self.content)
        return self._resolve_mentions(mentions, "channel")

    def _resolve_mentions(self, mentions, type_: str):
        """
        Resolves the mentions for this message.
        """
        final_mentions = []
        for mention in mentions:
            if type_ == "member":
                id = int(mention["id"])
                obb = self.guild.members.get(id)
                if obb is None:
                    obb = dt_user.User(**mention)
            elif type_ == "role":
                obb = self.guild.roles.get(int(mention))
            elif type_ == "channel":
                obb = self.guild.channels.get(int(mention))
            if obb is not None:
                final_mentions.append(obb)

        return final_mentions

    def reacted(self, emoji: 'typing.Union[dt_emoji.Emoji, str]') -> bool:
        """
        Checks if this message was reacted to with the specified emoji.

        :param emoji: The emoji to check.
        """
        for reaction in self.reactions:
            if reaction.emoji == emoji:
                return True

        return False

    # Message methods
    async def delete(self):
        """
        Deletes this message.

        You must have MANAGE_MESSAGE permissions to delete this message, or have it be your own message.
        """
        if self.guild is None:
            me = self._bot.user.id
            has_manage_messages = False
        else:
            me = self.guild.me.id
            has_manage_messages = self.channel.permissions(self.guild.me).manage_messages

        if self.id != me and not has_manage_messages:
            raise PermissionsError("manage_messages")

        await self._bot.http.delete_message(self.channel.id, self.id)

    async def edit(self, new_content: str = None, *,
                   embed: Embed = None) -> 'Message':
        """
        Edits this message.

        You must be the owner of this message to edit it.

        :param new_content: The new content for this message.
        :param embed: The new embed to provide.
        :return: This message, but edited with the new content.
        """
        if self.guild is None:
            is_me = self.author not in self.channel.recipients
        else:
            is_me = self.guild.me == self.author

        if not is_me:
            raise CuriousError("Cannot edit messages from other users")

        if embed:
            embed = embed.to_dict()

        # Prevent race conditions by spawning a listener, then waiting for the task once we've sent the HTTP request.
        t = await curio.spawn(self._bot.wait_for("message_edit", predicate=lambda o, n: n.id == self.id))
        try:
            await self._bot.http.edit_message(self.channel.id, self.id, content=new_content, embed=embed)
        except:
            await t.cancel()
            raise
        old, new = await t.join()
        return new

    async def pin(self):
        """
        Pins this message.

        You must have MANAGE_MESSAGES in the channel to pin the message.
        """
        if self.guild is not None:
            if not self.channel.permissions(self.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        await self._bot.http.pin_message(self.channel.id, self.id)

    async def unpin(self):
        """
        Unpins this message.

        You must have MANAGE_MESSAGES in this channel to unpin the message.
        Additionally, the message must already be pinned.
        """
        if self.guild is not None:
            if not self.channel.permissions(self.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        await self._bot.http.unpin_message(self.channel.id, self.id)

    async def get_who_reacted(self, emoji: 'typing.Union[dt_emoji.Emoji, str]') \
            -> 'typing.List[typing.Union[dt_user.User, dt_member.Member]]':
        """
        Fetches who reacted to this message.

        :param emoji: The emoji to check.
        :return: A list of either :class:`~.Member` or :class:`~.User` that reacted to this message.
        """
        if isinstance(emoji, dt_emoji.Emoji):
            emoji = "{}:{}".format(emoji.name, emoji.id)

        reactions = await self._bot.http.get_reaction_users(self.channel.id, self.id, emoji)
        result = []

        for user in reactions:
            member_id = int(user.get("id"))
            if self.guild is None:
                result.append(dt_user.User(self._bot, **user))
            else:
                member = self.guild.members.get(member_id)
                if not member:
                    result.append(dt_user.User(self._bot, **user))
                else:
                    result.append(member)

        return result

    async def react(self, emoji: 'typing.Union[dt_emoji.Emoji, str]'):
        """
        Reacts to a message with an emoji.

        This requires an Emoji object for reacting to messages with custom reactions, or a string containing the
        literal unicode (e.g ™) for normal emoji reactions.

        :param emoji: The emoji to react with.
        """
        if self.guild:
            if not self.channel.permissions(self.guild.me).add_reactions:
                # we can still add already reacted emojis
                # so make sure to check for that
                if not self.reacted(emoji):
                    raise PermissionsError("add_reactions")

        if isinstance(emoji, dt_emoji.Emoji):
            # undocumented!
            emoji = "{}:{}".format(emoji.name, emoji.id)

        await self._bot.http.react_to_message(self.channel.id, self.id, emoji)

    async def unreact(self, reaction: 'typing.Union[dt_emoji.Emoji, str]', victim: 'dt_member.Member' = None):
        """
        Removes a reaction from a user.

        :param reaction: The reaction to remove.
        :param victim: The victim to remove the reaction of. Can be None to signify ourselves.
        """
        if not self.guild:
            if victim and victim != self:
                raise CuriousError("Cannot delete other reactions in a DM")

        if victim and victim != self:
            if not self.channel.permissions(self.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        if isinstance(reaction, dt_emoji.Emoji):
            emoji = "{}:{}".format(reaction.name, reaction.id)
        else:
            emoji = reaction

        await self._bot.http.delete_reaction(self.channel.id, self.id, emoji, victim=victim.id if victim else None)

    async def remove_all_reactions(self):
        """
        Removes all reactions from a message.
        """
        if not self.guild:
            raise CuriousError("Cannot delete other reactions in a DM")

        if not self.channel.permissions(self.guild.me).manage_messages:
            raise PermissionsError("manage_messages")

        await self._bot.http.delete_all_reactions(self.channel.id, self.id)
