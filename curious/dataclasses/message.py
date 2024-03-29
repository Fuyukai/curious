# This file is part of curious.
#
# curious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# curious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with curious.  If not, see <http://www.gnu.org/licenses/>.

"""
Wrappers for Message objects.

.. currentmodule:: curious.dataclasses.message
"""
from __future__ import annotations

import datetime
import enum
import re
from typing import Union, Optional, TYPE_CHECKING, List, AsyncIterator

from curious.dataclasses.bases import Dataclass
from curious.dataclasses.emoji import Emoji
from curious.dataclasses.user import User
from curious.dataclasses.attachment import Attachment
from curious.dataclasses.embed import Embed
from curious.exc import CuriousError, ErrorCode, HTTPException, PermissionsError
from curious.util import AsyncIteratorWrapper, to_datetime

if TYPE_CHECKING:
    from curious.dataclasses.guild import Guild
    from curious.dataclasses.member import Member
    from curious.dataclasses.channel import Channel
    from curious.dataclasses.role import Role
    from curious.dataclasses.webhook import Webhook
    from curious.dataclasses.invite import Invite

CHANNEL_REGEX = re.compile(r"<#([0-9]*)>")
INVITE_REGEX = re.compile(r"discord\.gg/(\S+)|discordapp\.com/invites/(\S+)")
EMOJI_REGEX = re.compile(r"<a?:([\S]+):([0-9]+)>")
MENTION_REGEX = re.compile(r"<@!?([0-9]+)>")


class MessageType(enum.IntEnum):
    """
    Represents the type of a message.
    """

    #: The default (i.e. user message) type.
    DEFAULT = 0

    # 1 through 5 are groups only
    #: The recipient add type, used when a recipient is added to a group.
    RECIPIENT_ADD = 1

    #: The recipient remove type, used when a recipient is added to a group.
    RECIPIENT_REMOVE = 2

    #: The call type, used when a call is started.
    CALL = 3

    #: The channel name change type, used when a group channel name is changed.
    CHANNEL_NAME_CHANGE = 4

    #: The channel icon change type, used when a group channel icon is changed.
    CHANNEL_ICON_CHANGE = 5

    #: The channel pinned message type, used when a message is pinned.
    CHANNEL_PINNED_MESSAGE = 6

    #: The guild member join type, used when a member joins a guild.
    GUILD_MEMBER_JOIN = 7

    # TODO: Document these
    USER_PREMIUM_GUILD_SUBSCRIPTION = 8
    USER_PREMIUM_GUILD_SUBSCRIPTION_TIER_1 = 9
    USER_PREMIUM_GUILD_SUBSCRIPTION_TIER_2 = 10
    USER_PREMIUM_GUILD_SUBSCRIPTION_TIER_3 = 11
    CHANNEL_FOLLOW_ADD = 12
    GUILD_DISCOVERY_DISQUALIFIED = 14
    GUILD_DISCOVERY_REQUALIFIED = 15
    GUILD_DISCOVERY_GRACE_PERIOD_INITIAL_WARNING = 16
    GUILD_DISCOVERY_GRACE_PERIOD_FINAL_WARNING = 17
    THREAD_CREATED = 18
    REPLY = 19
    APPLICATION_COMMAND = 20
    THREAD_STARTER_MESSAGE = 21
    GUILD_INVITE_REMINDER = 22


class Message(Dataclass):
    """
    Represents a Message.
    """

    __slots__ = (
        "content",
        "guild_id",
        "author",
        "created_at",
        "edited_at",
        "embeds",
        "attachments",
        "_mentions",
        "_role_mentions",
        "reactions",
        "channel_id",
        "author_id",
        "type",
    )

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.get("id"), client)

        #: The content of the message.
        self.content: str = kwargs["content"]

        #: The ID of the guild this message is in.
        self.guild_id: Optional[int] = None

        #: The ID of the channel the message was sent in.
        self.channel_id: int = int(kwargs["channel_id"])

        #: The ID of the author.
        self.author_id: int = int(kwargs.get("author", {}).get("id", 0)) or None

        #: The author of this message. Can be one of: :class:`.Member`, :class:`.Webhook`,
        #: :class:`.User`.
        self.author: Union[Member, Webhook, User] = None

        type_ = kwargs.get("type", 0)
        #: The type of this message.
        self.type = MessageType(type_)

        #: The true timestamp of this message, a :class:`datetime.datetime`.
        #: This is not the snowflake timestamp.
        self.created_at: datetime.datetime = to_datetime(kwargs.get("timestamp", None))

        #: The edited timestamp of this message.
        #: This can sometimes be None.
        self.edited_at: datetime.datetime

        edited_timestamp = kwargs.get("edited_timestamp", None)
        if edited_timestamp is not None:
            self.edited_at = to_datetime(edited_timestamp)
        else:
            self.edited_at = None

        #: The list of :class:`.Embed` objects this message contains.
        self.embeds: List[Embed] = []
        for embed in kwargs.get("embeds", []):
            self.embeds.append(Embed(**embed))

        #: The list of :class:`.Attachment` this message contains.
        self.attachments: List[Attachment] = []

        for attachment in kwargs.get("attachments", []):
            self.attachments.append(Attachment(bot=self._bot, **attachment))

        #: The mentions for this message.
        #: This is UNORDERED.
        self._mentions = kwargs.get("mentions", [])

        #: The role mentions for this message.
        #: This is UNORDERED.
        self._role_mentions = kwargs.get("mention_roles", [])

        #: The reactions for this message.
        self.reactions = []

    def __repr__(self) -> str:
        return "<{0.__class__.__name__} id={0.id} content='{0.content}'>".format(self)

    def __str__(self) -> str:
        return self.content

    @property
    def guild(self) -> Optional[Guild]:
        """
        :return: The :class:`.Guild` this message is associated with.
        """
        return self.channel.guild

    @property
    def channel(self) -> Channel:
        """
        :return: The :class:`.Channel` this message is associated with.
        """
        return self._bot.state.find_channel(self.channel_id)

    @property
    def mentions(self) -> List[Member]:
        """
        Returns a list of :class:`.Member` that were mentioned in this message.

        .. warning::

            The mentions in this will **not** be in order. Discord does not return them in any
            particular order.

        """
        return self._resolve_mentions(self._mentions, "member")

    @property
    def role_mentions(self) -> List[Role]:
        """
        Returns a list of :class:`.Role` that were mentioned in this message.

        .. warning::

            The mentions in this will **not** be in order. Discord does not return them in any
            particular order.

        """

        return self._resolve_mentions(self._role_mentions, "role")

    @property
    def channel_mentions(self) -> List[Channel]:
        """
        Returns a list of :class:`.Channel` that were mentioned in this message.

        .. note::

            These mentions **are** in order. They are parsed from the message content.

        """
        mentions = CHANNEL_REGEX.findall(self.content)
        return self._resolve_mentions(mentions, "channel")

    @property
    def emojis(self) -> List[Emoji]:
        """
        Returns a list of :class:`.Emoji` that was found in this message.
        """
        matches = EMOJI_REGEX.findall(self.content)
        emojis = []

        for (name, i) in matches:
            e = self.guild.emojis.get(int(i))
            if e:
                emojis.append(e)

        return emojis

    async def clean_content(self) -> str:
        """
        Gets the cleaned content for this message.
        """
        return await self._bot.clean_content(self.content)

    async def get_invites(self) -> List[Invite]:
        """
        Gets a list of valid invites in this message.
        """
        invites = INVITE_REGEX.findall(self.content)
        obbs = []
        for match in invites:
            if match[0]:
                code = match[0]
            else:
                code = match[1]

            try:
                obbs.append(await self._bot.get_invite(code))
            except HTTPException as e:
                if e.error_code != ErrorCode.UNKNOWN_INVITE:
                    raise

        return obbs

    @property
    def invites(self) -> AsyncIterator[Invite]:
        """
        Returns a list of :class:`.Invite` objects that are in this message (and valid).
        """
        return AsyncIteratorWrapper(self.get_invites)

    def _resolve_mentions(
        self,
        mentions,
        type_,
    ):
        """
        Resolves the mentions for this message.

        :param mentions: The mentions to resolve; a list of dicts or ints.
        :param type_: The type of mention to resolve: ``channel``, ``role``, or ``member``.
        """
        final_mentions = []
        for mention in mentions:
            obb = None
            if type_ == "member":
                user_id = int(mention["id"])
                if self.guild_id:
                    cache_finder = self.guild.members.get
                else:
                    cache_finder = self._bot.state._users.get

                obb = cache_finder(user_id)

                if obb is None:
                    obb = self._bot.state.make_user(mention)
                    # always check for a decache
                    self._bot.state._check_decache_user(user_id)

            elif type_ == "role":
                if self.guild_id is None:
                    return []

                obb = self.guild.roles.get(int(mention))
            elif type_ == "channel":
                if self.guild_id is None:
                    return []

                obb = self.guild.channels.get(int(mention))

            if obb is not None:
                final_mentions.append(obb)

        return final_mentions

    def reacted(self, emoji: Union[Emoji, str]) -> bool:
        """
        Checks if this message was reacted to with the specified emoji.

        :param emoji: The emoji to check.
        """
        for reaction in self.reactions:
            if reaction.emoji == emoji:
                return True

        return False

    # Message methods
    async def delete(self) -> None:
        """
        Deletes this message.

        You must have MANAGE_MESSAGE permissions to delete this message, or have it be your own
        message.
        """
        if self.guild is None:
            me = self._bot.user.id
            has_manage_messages = False
        else:
            me = self.guild.me.id
            has_manage_messages = self.channel.effective_permissions(self.guild.me).manage_messages

        if self.id != me and not has_manage_messages:
            raise PermissionsError("manage_messages")

        await self._bot.http.delete_message(self.channel.id, self.id)

    async def edit(self, new_content: str = None, *, embed: Embed = None) -> "Message":
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

        async with self._bot.events.wait_for_manager(
            "message_update", lambda o, n: n.id == self.id
        ):
            await self._bot.http.edit_message(
                self.channel.id, self.id, content=new_content, embed=embed
            )
        return self

    async def pin(self) -> Message:
        """
        Pins this message.

        You must have MANAGE_MESSAGES in the channel to pin the message.
        """
        if self.guild is not None:
            if not self.channel.effective_permissions(self.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        await self._bot.http.pin_message(self.channel.id, self.id)
        return self

    async def unpin(self) -> Message:
        """
        Unpins this message.

        You must have MANAGE_MESSAGES in this channel to unpin the message.
        Additionally, the message must already be pinned.
        """
        if self.guild is not None:
            if not self.channel.effective_permissions(self.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        await self._bot.http.unpin_message(self.channel.id, self.id)
        return self

    async def get_who_reacted(
        self,
        emoji: Union[Emoji, str],
    ) -> List[Union[User, Member]]:
        """
        Fetches who reacted to this message.

        :param emoji: The emoji to check.
        :return: A list of either :class:`.Member` or :class:`.User` that reacted to this message.
        """
        if not isinstance(emoji, str):
            emoji = "{}:{}".format(emoji.name, emoji.id)

        reactions = await self._bot.http.get_reaction_users(self.channel.id, self.id, emoji)
        result = []

        for user in reactions:
            member_id = int(user.get("id"))
            if self.guild is None:
                result.append(User(self._bot, **user))
            else:
                member = self.guild.members.get(member_id)
                if not member:
                    result.append(User(self._bot, **user))
                else:
                    result.append(member)

        return result

    async def react(self, emoji: Union[Emoji, str]):
        """
        Reacts to a message with an emoji.

        This requires an Emoji object for reacting to messages with custom reactions, or a string
        containing the literal unicode (e.g ™) for normal emoji reactions.

        :param emoji: The emoji to react with.
        """
        if self.guild:
            if not self.channel.effective_permissions(self.guild.me).add_reactions:
                # we can still add already reacted emojis
                # so make sure to check for that
                if not self.reacted(emoji):
                    raise PermissionsError("add_reactions")

        if not isinstance(emoji, str):
            # undocumented!
            emoji = "{}:{}".format(emoji.name, emoji.id)

        await self._bot.http.add_reaction(self.channel.id, self.id, emoji)

    async def unreact(self, reaction: Union[Emoji, str], victim: Member = None):
        """
        Removes a reaction from a user.

        :param reaction: The reaction to remove.
        :param victim: The victim to remove the reaction of. Can be None to signify ourselves.
        """
        if not self.guild:
            if victim and victim != self:
                raise CuriousError("Cannot delete other reactions in a DM")

        if victim and victim != self:
            if not self.channel.effective_permissions(self.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        if not isinstance(reaction, str):
            emoji = "{}:{}".format(reaction.name, reaction.id)
        else:
            emoji = reaction

        await self._bot.http.delete_reaction(
            self.channel.id, self.id, emoji, victim=victim.id if victim else None
        )

    async def remove_all_reactions(self) -> None:
        """
        Removes all reactions from a message.
        """
        if not self.guild:
            raise CuriousError("Cannot delete other reactions in a DM")

        if not self.channel.effective_permissions(self.guild.me).manage_messages:
            raise PermissionsError("manage_messages")

        await self._bot.http.delete_all_reactions(self.channel.id, self.id)
