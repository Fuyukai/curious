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
Wrappers for Channel objects.

.. currentmodule:: curious.dataclasses.channel
"""
import collections
import enum
import pathlib
import time
import typing as _typing
from math import floor
from os import PathLike
from types import MappingProxyType
from typing import AsyncIterator

import multio
from async_generator import asynccontextmanager

from curious.dataclasses import guild as dt_guild, invite as dt_invite, member as dt_member, \
    message as dt_message, permissions as dt_permissions, role as dt_role, user as dt_user, \
    webhook as dt_webhook
from curious.dataclasses.bases import Dataclass, IDObject
from curious.dataclasses.embed import Embed
from curious.exc import CuriousError, ErrorCode, Forbidden, HTTPException, PermissionsError
from curious.util import AsyncIteratorWrapper, base64ify, deprecated, safe_generator


class ChannelType(enum.IntEnum):
    """
    Returns a mapping from Discord channel type.
    """

    #: Represents a text channel.
    TEXT = 0

    #: Represents a private channel.
    PRIVATE = 1

    #: Represents a voice channel.
    VOICE = 2

    #: Represents a group channel.
    GROUP = 3

    #: Represents a category channel.
    CATEGORY = 4

    def has_messages(self) -> bool:
        """
        :return: If this channel type has messages.
        """
        return self not in [ChannelType.VOICE, ChannelType.CATEGORY]


class HistoryIterator(collections.AsyncIterator):
    """
    An iterator that allows you to automatically fetch messages and async iterate over them.
    
    .. code-block:: python3
    
        it = HistoryIterator(some_channel, bot, max_messages=100)
        
        # usage 1
        async for message in it:
            ...
            
        # usage 2
        await it.fill_messages()
        for message in it.messages:
            ...
            
    Note that usage 2 will only fill chunks of 100 messages at a time.
    """

    def __init__(self, channel: 'Channel',
                 max_messages: int = -1, *,
                 before: int = None, after: int = None):
        """
        :param channel: The :class:`.Channel` to iterate over.
        :param max_messages: The maximum number of messages to return. <= 0 means infinite.
        :param before: The message ID to fetch before.
        :param after: The message ID to fetch after.

        .. versionchanged:: 0.7.0

            Removed the ``client`` parameter.
        """
        self.channel = channel

        #: The current storage of messages.
        self.messages = collections.deque()

        #: The current count of messages iterated over.
        #: This is used to know when to automatically fill new messages.
        self.current_count = 0

        #: The maximum amount of messages to use.
        #: If this is <= 0, an infinite amount of messages are returned.
        self.max_messages = max_messages

        #: The message ID of before to fetch.
        self.before = before
        if isinstance(self.before, IDObject):
            self.before = self.before.id

        #: The message ID of after to fetch.
        self.after = after
        if isinstance(self.after, IDObject):
            self.after = self.after.id

        #: The last message ID that we fetched.
        if self.before:
            self.last_message_id = self.before
        else:
            self.last_message_id = self.after

    async def fill_messages(self) -> None:
        """
        Called to fill the next <n> messages.
        
        This is called automatically by :meth:`.__anext__`, but can be used to fill the messages
        anyway.
        """
        if self.max_messages < 0:
            to_get = 100
        else:
            to_get = self.max_messages - self.current_count

        if to_get <= 0:
            return

        if self.before:
            messages = await self.channel._bot.http.get_message_history(self.channel.id,
                                                                        before=self.last_message_id,
                                                                        limit=to_get)
        else:
            messages = await self.channel._bot.http.get_message_history(self.channel.id,
                                                                        after=self.last_message_id)
            messages = reversed(messages)

        for message in messages:
            self.messages.append(self.channel._bot.state.make_message(message))

    async def __anext__(self) -> 'dt_message.Message':
        self.current_count += 1
        if self.current_count == self.max_messages:
            raise StopAsyncIteration

        if len(self.messages) <= 0:
            await self.fill_messages()

        try:
            message = self.messages.popleft()
        except IndexError:
            # No messages to fill, so self._fill_messages didn't return any
            # This signals the end of iteration.
            raise StopAsyncIteration
        self.last_message_id = message.id

        return message

    def __iter__(self) -> None:
        raise RuntimeError("This is not an iterator - you want to use `async for` instead.")

    def __await__(self) -> None:
        raise RuntimeError("This is not a coroutine - you want to use `async for` instead.")

    async def next(self) -> 'dt_message.Message':
        """
        Gets the next item in history.
        """
        return await self.__anext__()

    async def all(self) -> '_typing.List[dt_message.Message]':
        """
        Gets a flattened list of items from the history.
        """
        items = []

        async for item in self:
            items.append(item)

        return items


class ChannelMessageWrapper(object):
    """
    Represents a channel's message container.
    """

    __slots__ = "channel",

    def __init__(self, channel: 'Channel'):
        #: The :class:`.Channel` this container is used for.
        self.channel = channel

    def __iter__(self) -> None:
        raise RuntimeError("Use `async for`")

    def __aiter__(self) -> HistoryIterator:
        return self.history.__aiter__()

    @property
    def history(self) -> HistoryIterator:
        """
        :return: A :class:`.HistoryIterator` that can be used to iterate over the channel history.
        """
        return self.get_history(before=self.channel._last_message_id, limit=-1)

    def get_history(self, before: int = None,
                    after: int = None,
                    limit: int = 100) -> HistoryIterator:
        """
        Gets history for this channel.

        This is *not* an async function - it returns a :class:`HistoryIterator` which can be async
        iterated over to get message history.

        .. code-block:: python3

            async for message in channel.get_history(limit=1000):
                print(message.content, "by", message.author.user.name)

        :param limit: The maximum number of messages to get.
        :param before: The snowflake ID to get messages before.
        :param after: The snowflake ID to get messages after.
        """
        if self.channel.guild:
            if not self.channel.permissions(self.channel.guild.me).read_message_history:
                raise PermissionsError("read_message_history")

        return HistoryIterator(self.channel, before=before, after=after, max_messages=limit)

    async def send(self, content: str = None, *,
                   tts: bool = False, embed: 'Embed' = None) -> 'dt_message.Message':
        """
        Sends a message to this channel.

        This requires SEND_MESSAGES permission in the channel.
        If the content is not a string, it will be automatically stringified.

        .. code:: python

            await channel.send("Hello, world!")

        :param content: The content of the message to send.
        :param tts: Should this message be text to speech?
        :param embed: An embed object to send with this message.
        :return: A new :class:`.Message` object.
        """
        if not self.channel.type.has_messages():
            raise CuriousError("Cannot send messages to a voice channel")

        if self.channel.guild:
            if not self.channel.permissions(self.channel.guild.me).send_messages:
                raise PermissionsError("send_messages")

        if not isinstance(content, str) and content is not None:
            content = str(content)

        # check for empty messages
        if not content:
            if not embed:
                raise CuriousError("Cannot send an empty message")

            if self.channel.guild and not \
                    self.channel.permissions(self.channel.guild.me).embed_links:
                raise PermissionsError("embed_links")
        else:
            if content and len(content) > 2000:
                raise CuriousError("Content must be less than 2000 characters")

        if embed is not None:
            embed = embed.to_dict()

        data = await self.channel._bot.http.send_message(self.channel.id, content,
                                                         tts=tts, embed=embed)
        obb = self.channel._bot.state.make_message(data, cache=True)

        return obb

    async def upload(self, fp: '_typing.Union[bytes, str, PathLike, _typing.IO]',
                     *,
                     filename: str = None,
                     message_content: '_typing.Optional[str]' = None) -> 'dt_message.Message':
        """
        Uploads a message to this channel.

        This requires SEND_MESSAGES and ATTACH_FILES permission in the channel.

        .. code-block:: python3

            with open("/tmp/emilia_best_girl.jpg", 'rb') as f:
                await channel.messages.upload(f, "my_waifu.jpg")

        :param fp: Variable.

            - If passed a string or a :class:`os.PathLike`, will open and read the file and
            upload it.
            - If passed bytes, will use the bytes as the file content.
            - If passed a file-like, will read and use the content to upload.

        :param filename: The filename for the file uploaded. If a path-like or str is passed, \
            will use the filename from that if this is not specified.
        :param message_content: Optional: Any extra content to be sent with the message.
        :return: The new :class:`.Message` created.
        """
        if not self.channel.type.has_messages():
            raise CuriousError("Cannot send messages to a voice channel")

        if self.channel.guild:
            if not self.channel.permissions(self.channel.guild.me).send_messages:
                raise PermissionsError("send_messages")

            if not self.channel.permissions(self.channel.guild.me).attach_files:
                raise PermissionsError("attach_files")

        if isinstance(fp, bytes):
            file_content = fp
        elif isinstance(fp, pathlib.Path):
            if filename is None:
                filename = fp.parts[-1]

            file_content = fp.read_bytes()
        elif isinstance(fp, (str, PathLike)):
            path = pathlib.Path(fp)
            if filename is None:
                filename = path.parts[-1]

            file_content = path.read_bytes()
        elif isinstance(fp, _typing.IO) or hasattr(fp, "read"):
            file_content = fp.read()

            if isinstance(file_content, str):
                file_content = file_content.encode("utf-8")
        else:
            raise ValueError("Got unknown type for upload")

        if filename is None:
            filename = "unknown.bin"

        data = await self.channel._bot.http.send_file(self.channel.id, file_content,
                                                      filename=filename, content=message_content)
        obb = self.channel._bot.state.make_message(data, cache=False)
        return obb

    async def bulk_delete(self, messages: '_typing.List[dt_message.Message]') -> int:
        """
        Deletes messages from a channel.
        This is the low-level delete function - for the high-level function, see
        :meth:`.Channel.messages.purge()`.

        Example for deleting all the last 100 messages:

        .. code:: python

            history = channel.messages.get_history(limit=100)
            messages = []

            async for message in history:
                messages.append(message)

            await channel.messages.bulk_delete(messages)

        :param messages: A list of :class:`.Message` objects to delete.
        :return: The number of messages deleted.
        """
        if self.channel.guild:
            if not self.channel.permissions(self.channel.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        minimum_allowed = floor((time.time() - 14 * 24 * 60 * 60) * 1000.0 - 1420070400000) << 22
        ids = []
        for message in messages:
            if message.id < minimum_allowed:
                msg = f"Cannot delete message id {message.id} older than {minimum_allowed}"
                raise CuriousError(msg)

            ids.append(message.id)

        await self.channel._bot.http.delete_multiple_messages(self.channel.id, ids)

        return len(ids)

    async def purge(self, limit: int = 100, *,
                    author: 'dt_member.Member' = None,
                    content: str = None,
                    predicate: '_typing.Callable[[dt_message.Message], bool]' = None,
                    fallback_from_bulk: bool = False):
        """
        Purges messages from a channel.
        This will attempt to use ``bulk-delete`` if possible, but otherwise will use the normal
        delete endpoint (which can get ratelimited severely!) if ``fallback_from_bulk`` is True.

        Example for deleting all messages owned by the bot:

        .. code-block:: python3

            me = channel.guild.me
            await channel.messages.purge(limit=100, author=me)

        Custom check functions can also be applied which specify any extra checks. They take one
        argument (the Message object) and return a boolean (True or False) determining if the
        message should be deleted.

        For example, to delete all messages with the letter ``i`` in them:

        .. code-block:: python3

            await channel.messages.purge(limit=100,
                                         predicate=lambda message: 'i' in message.content)

        :param limit: The maximum amount of messages to delete. -1 for unbounded size.
        :param author: Only delete messages made by this author.
        :param content: Only delete messages that exactly match this content.
        :param predicate: A callable that determines if a message should be deleted.
        :param fallback_from_bulk: If this is True, messages will be regular deleted if they \
            cannot be bulk deleted.
        :return: The number of messages deleted.
        """
        if self.channel.guild:
            if not self.channel.permissions(self.channel.guild.me).manage_messages \
                    and not fallback_from_bulk:
                raise PermissionsError("manage_messages")

        checks = []
        if author:
            checks.append(lambda m: m.author == author)

        if content:
            checks.append(lambda m: m.content == content)

        if predicate:
            checks.append(predicate)

        to_delete = []
        history = self.get_history(limit=limit)

        async for message in history:
            if all(check(message) for check in checks):
                to_delete.append(message)

        can_bulk_delete = True

        # Split into chunks of 100.
        message_chunks = [to_delete[i:i + 100] for i in range(0, len(to_delete), 100)]
        minimum_allowed = floor((time.time() - 14 * 24 * 60 * 60) * 1000.0 - 1420070400000) << 22
        for chunk in message_chunks:
            message_ids = []
            for message in chunk:
                if message.id < minimum_allowed:
                    msg = f"Cannot delete message id {message.id} older than {minimum_allowed}"
                    raise CuriousError(msg)

                message_ids.append(message.id)

            # First, try and bulk delete all the messages.
            if can_bulk_delete:
                try:
                    await self.channel._bot.http.delete_multiple_messages(self.channel.id,
                                                                          message_ids)
                except Forbidden:
                    # We might not have MANAGE_MESSAGES.
                    # Check if we should fallback on normal delete.
                    can_bulk_delete = False
                    if not fallback_from_bulk:
                        # Don't bother, actually.
                        raise

            # This is an `if not` instead of an `else` because `can_bulk_delete` might've changed.
            if not can_bulk_delete:
                # Instead, just delete() the message.
                for message in chunk:
                    await message.delete()

        return len(to_delete)

    async def get(self, message_id: int) -> 'dt_message.Message':
        """
        Gets a single message from this channel.

        .. versionchanged:: 0.7.0

            Errors raised are now consistent across bots and userbots.

        :param message_id: The message ID to retrieve.
        :return: A new :class:`.Message` object.
        :raises CuriousError: If the message could not be found.
        """
        if self.channel.guild:
            if not self.channel.permissions(self.channel.guild.me).read_message_history:
                raise PermissionsError("read_message_history")

        cached_message = self.channel._bot.state.find_message(message_id)
        if cached_message is not None:
            return cached_message

        try:
            data = await self.channel._bot.http.get_message(self.channel.id, message_id)
        except HTTPException as e:
            # transform into a CuriousError if it wasn't found
            if e.error_code == ErrorCode.UNKNOWN_MESSAGE:
                raise CuriousError("No message found for this ID") from e

            raise

        msg = self.channel._bot.state.make_message(data)

        return msg


class Channel(Dataclass):
    """
    Represents a channel object.
    """

    def __init__(self, client, **kwargs) -> None:
        super().__init__(kwargs.get("id"), client)

        #: The name of this channel.
        self.name = kwargs.get("name", None)  # type: str

        #: The topic of this channel.
        self.topic = kwargs.get("topic", None)  # type: str

        #: The ID of the guild this is associated with.
        self.guild_id = int(kwargs.get("guild_id", 0)) or None  # type: int

        parent_id = kwargs.get("parent_id")
        if parent_id is not None:
            parent_id = int(parent_id)

        #: The parent ID of this channel.
        self.parent_id = parent_id  # type: int

        #: The :class:`.ChannelType` of channel this channel is.
        self.type = ChannelType(kwargs.get("type", 0))  # type: ChannelType

        #: The :class:`.ChannelMessageWrapper` for this channel.
        self._messages = None  # type: ChannelMessageWrapper

        #: If this channel is NSFW.
        self.nsfw = kwargs.get("nsfw", False)  # type: bool

        #: If private, the mapping of :class:`.User` that are in this channel.
        self._recipients = {}  # type: _typing.Dict[int, dt_user.User]

        if self.private:
            for recipient in kwargs.get("recipients", []):
                u = self._bot.state.make_user(recipient)
                self._recipients[u.id] = u

            if self.type == ChannelType.GROUP:
                # append the current user
                self._recipients[self._bot.user.id] = self._bot.user

        #: The position of this channel.
        self.position = kwargs.get("position", 0)  # type: int

        #: The last message ID of this channel.
        #: Used for history.
        self._last_message_id = None  # type: int

        _last_message_id = kwargs.get("last_message_id", 0)
        if _last_message_id:
            self._last_message_id = int(_last_message_id)
        else:
            self._last_message_id = None

        # group channel stuff
        #: The owner ID of the channel.
        #: This is None for non-group channels.
        self.owner_id = int(kwargs.get("owner_id", 0)) or None  # type: int

        #: The icon hash of the channel.
        self.icon_hash = kwargs.get("icon", None)  # type: str

        #: The internal overwrites for this channel.
        self._overwrites = {}  # type: _typing.Dict[int, dt_permissions.Overwrite]

    def __repr__(self) -> str:
        return f"<Channel id={self.id} name={self.name} type={self.type.name} " \
               f"guild_id={self.guild_id}>"

    __str__ = __repr__

    def _update_overwrites(self, overwrites: _typing.List[dict]):
        """
        Updates the overwrites for this channel.

        :param overwrites: A list of overwrite dicts.
        """
        if not self.guild_id:
            raise CuriousError("A channel without a guild cannot have overwrites")

        self._overwrites = {}

        for overwrite in overwrites:
            id_ = int(overwrite["id"])
            type_ = overwrite["type"]

            if type_ == "member":
                obb = self.guild._members.get(id_)
            else:
                obb = self.guild._members.get(id_)

            self._overwrites[id] = dt_permissions.Overwrite(allow=overwrite["allow"],
                                                            deny=overwrite["deny"],
                                                            obb=obb, channel_id=self.id)

    @property
    def guild(self) -> '_typing.Union[dt_guild.Guild, None]':
        """
        :return: The :class:`.Guild` associated with this Channel.
        """
        try:
            return self._bot.guilds[self.guild_id]
        except KeyError:
            return None

    @property
    def private(self) -> bool:
        """
        :return: If this channel is a private channel (i.e has no guild.)
        """
        return self.guild_id is None

    @property
    def recipients(self) -> '_typing.Mapping[int, dt_user.User]':
        """
        :return: A mapping of int -> :class:`.User` for the recipients of this private chat.
        """
        return MappingProxyType(self._recipients)

    @property
    def user(self) -> '_typing.Union[dt_user.User, None]':
        """
        :return: If this channel is a private channel, the :class:`.User` of the other user.
        """
        if self.type != ChannelType.PRIVATE:
            return None

        try:
            return next(iter(self.recipients.values()))
        except StopIteration:
            return None

    @property
    def owner(self) -> '_typing.Union[dt_user.User, None]':
        """
        :return: If this channel is a group channel, the owner of the channel.
        """
        if not self.owner_id:
            return None

        try:
            return self._bot.state._users[self.owner_id]
        except KeyError:
            return None

    @property
    def parent(self) -> '_typing.Union[Channel, None]':
        """
        :return: If this channel has a parent, the parent category of this channel.
        """
        try:
            return self.guild.channels[self.parent_id]
        except (KeyError, AttributeError):
            return None

    @property
    def children(self) -> '_typing.List[Channel]':
        """
        :return: A list of :class:`.Channel` children this channel has, if any.
        """
        if not self.guild:
            return []

        channels = [channel
                    for channel in self.guild.channels.values()
                    if channel.parent_id == self.id]
        return channels

    def get_by_name(self, name: str) -> '_typing.Union[Channel, None]':
        """
        Gets a channel by name in this channel's children.

        :param name: The name of the channel to get.
        :return: A :class:`.Channel` if the channel was find
        """
        return next(filter(lambda channel: channel.name == name, self.children), None)

    @property
    def messages(self) -> 'ChannelMessageWrapper':
        """
        :return: The :class:`.ChannelMessageWrapper` for this channel, if applicable.
        """
        if not self.type.has_messages():
            raise CuriousError("This channel does not have messages")

        if self._messages is None:
            self._messages = ChannelMessageWrapper(self)
        return self._messages

    @property
    @deprecated(since="0.7.0", see_instead="Channel.messages", removal="0.9.0")
    def history(self) -> HistoryIterator:
        """
        :return: A :class:`.HistoryIterator` that can be used to iterate over the channel history.
        """
        return self.messages.history

    @property
    def pins(self) -> '_typing.AsyncIterator[dt_message.Message]':
        """
        :return: A :class:`.AsyncIteratorWrapper` that can be used to iterate over the pins.
        """
        return AsyncIteratorWrapper(self.get_pins)

    @property
    def icon_url(self) -> _typing.Union[str, None]:
        """
        :return: The icon URL for this channel if it is a group DM. 
        """
        return "https://cdn.discordapp.com/channel-icons/{}/{}.webp" \
            .format(self.id, self.icon_hash)

    @property
    def voice_members(self) -> '_typing.List[dt_member.Member]':
        """
        :return: A list of members that are in this voice channel.
        """
        if self.type != ChannelType.VOICE:
            raise CuriousError("No members for channels that aren't voice channels")

        return list(
            filter(lambda member: member.voice.channel == self, self.guild.members.values())
        )

    @property
    def overwrites(self) -> '_typing.Mapping[int, dt_permissions.Overwrite]':
        """
        :return: A mapping of target_id -> :class:`.Overwrite` for this channel.
        """
        return MappingProxyType(self._overwrites)

    def permissions(self, obb: '_typing.Union[dt_member.Member, dt_role.Role]') -> \
            'dt_permissions.Overwrite':
        """
        Gets the permission overwrites for the specified object.
        """
        overwrite = self._overwrites.get(obb.id)
        if not overwrite:
            overwrite = dt_permissions.Overwrite(0, 0, obb)
            overwrite.channel_id = self.id

        return overwrite

    @property
    def me_permissions(self) -> 'dt_permissions.Overwrite':
        """
        :return: The overwrite permissions for the current member.
        """
        return self.permissions(self.guild.me)

    def _copy(self):
        obb = object.__new__(self.__class__)
        obb.name = self.name
        obb.type = self.type
        obb.guild_id = self.guild_id
        obb.nsfw = self.nsfw
        obb._recipients = self._recipients
        obb.icon_hash = self.icon_hash
        obb.owner_id = self.owner_id
        obb.topic = self.topic
        obb.position = self.position
        obb._bot = self._bot
        obb.parent_id = self.parent_id
        return obb

    @deprecated(since="0.7.0", see_instead="Channel.messages.get_history", removal="0.9.0")
    def get_history(self, before: int = None,
                    after: int = None,
                    limit: int = 100) -> HistoryIterator:
        """
        Gets history for this channel.

        This is *not* an async function - it returns a :class:`HistoryIterator` which can be async
        iterated over to get message history.

        .. code-block:: python3

            async for message in channel.get_history(limit=1000):
                print(message.content, "by", message.author.user.name)

        :param limit: The maximum number of messages to get.
        :param before: The snowflake ID to get messages before.
        :param after: The snowflake ID to get messages after.
        """
        return self.messages.get_history(before=before, after=after, limit=limit)

    async def get_pins(self) -> '_typing.List[dt_message.Message]':
        """
        Gets the pins for a channel.

        :return: A list of :class:`.Message` objects.
        """
        msg_data = await self._bot.http.get_pins(self.id)

        messages = []
        for message in msg_data:
            messages.append(self._bot.state.make_message(message))

        return messages

    @property
    def webhooks(self) -> 'AsyncIterator[dt_webhook.Webhook]':
        """
        :return: A :class:`.AsyncIteratorWrapper` for the :class:`.Webhook` objects in this \
            channel.
        """
        return AsyncIteratorWrapper(self.get_webhooks)

    async def get_webhooks(self) -> '_typing.List[dt_webhook.Webhook]':
        """
        Gets the webhooks for this channel.

        :return: A list of :class:`.Webhook` objects for the channel.
        """
        webhooks = await self._bot.http.get_webhooks_for_channel(self.id)
        obbs = []

        for webhook in webhooks:
            obbs.append(self._bot.state.make_webhook(webhook))

        return obbs

    @deprecated(since="0.7.0", see_instead="Channel.messages.get", removal="0.9.0")
    async def get_message(self, message_id: int) -> 'dt_message.Message':
        """
        Gets a single message from this channel.

        :param message_id: The message ID to retrieve.
        :return: A new :class:`.Message` object.
        """
        return await self.messages.get(message_id)

    async def create_webhook(self, *, name: str = None,
                             avatar: bytes = None) -> 'dt_webhook.Webhook':
        """
        Create a webhook in this channel.

        :param name: The name of the new webhook.
        :param avatar: The bytes content of the new webhook.
        :return: A :class:`.Webhook` that represents the webhook created.
        """
        if not self.permissions(self.guild.me).manage_webhooks:
            raise PermissionsError("manage_webhooks")

        if avatar is not None:
            avatar = base64ify(avatar)

        data = await self._bot.http.create_webhook(self.id, name=name, avatar=avatar)
        webook = self._bot.state.make_webhook(data)

        return webook

    async def edit_webhook(self, webhook: 'dt_webhook.Webhook', *,
                           name: str = None, avatar: bytes = None) -> 'dt_webhook.Webhook':
        """
        Edits a webhook.

        :param webhook: The :class:`.Webhook` to edit.
        :param name: The new name for the webhook.
        :param avatar: The new bytes for the avatar.
        :return: The modified :class:`.Webhook`. object.
        """
        if avatar is not None:
            avatar = base64ify(avatar)

        if webhook.token is not None:
            # Edit it unconditionally.
            await self._bot.http.edit_webhook_with_token(webhook.id, webhook.token,
                                                         name=name, avatar=avatar)

        if not self.permissions(self.guild.me).manage_webhooks:
            raise PermissionsError("manage_webhooks")

        data = await self._bot.http.edit_webhook(webhook.id,
                                                 name=name, avatar=avatar)
        webhook.default_name = data.get("name")
        webhook._default_avatar = data.get("avatar")

        webhook.user.username = data.get("name")
        webhook.user.avatar_hash = data.get("avatar")

        return webhook

    async def delete_webhook(self, webhook: 'dt_webhook.Webhook') -> 'dt_webhook.Webhook':
        """
        Deletes a webhook.

        You must have MANAGE_WEBHOOKS to delete this webhook.

        :param webhook: The :class:`.Webhook` to delete.
        """
        if webhook.token is not None:
            # Delete it unconditionally.
            await self._bot.http.delete_webhook_with_token(webhook.id, webhook.token)
            return webhook

        if not self.permissions(self.guild.me).manage_webhooks:
            raise PermissionsError("manage_webhooks")

        await self._bot.http.delete_webhook(webhook.id)
        return webhook

    async def create_invite(self, **kwargs) -> 'dt_invite.Invite':
        """
        Creates an invite in this channel.

        :param max_age: The maximum age of the invite.
        :param max_uses: The maximum uses of the invite.
        :param temporary: Is this invite temporary?
        :param unique: Is this invite unique?
        """
        if not self.guild:
            raise PermissionsError("create_instant_invite")

        if not self.permissions(self.guild.me).create_instant_invite:
            raise PermissionsError("create_instant_invite")

        inv = await self._bot.http.create_invite(self.id, **kwargs)
        invite = dt_invite.Invite(self._bot, **inv)

        return invite

    @deprecated(since="0.7.0", see_instead="Channel.messages.delete_messages",
                removal="0.9.0")
    async def delete_messages(self, messages: '_typing.List[dt_message.Message]') -> int:
        """
        Deletes messages from a channel.
        This is the low-level delete function - for the high-level function, see 
        :meth:`.Channel.purge()`.

        Example for deleting all the last 100 messages:

        .. code:: python

            history = channel.get_history(limit=100)
            messages = []

            async for message in history:
                messages.append(message)

            await channel.delete_messages(messages)

        :param messages: A list of :class:`.Message` objects to delete.
        :return: The number of messages deleted.
        """
        return await self.messages.bulk_delete(messages)

    @deprecated(since="0.7.0", see_instead="Channel.messages.purge", removal="0.9.0")
    async def purge(self, limit: int = 100, *,
                    author: 'dt_member.Member' = None,
                    content: str = None,
                    predicate: '_typing.Callable[[dt_message.Message], bool]' = None,
                    fallback_from_bulk: bool = False):
        """
        Purges messages from a channel.
        This will attempt to use ``bulk-delete`` if possible, but otherwise will use the normal
        delete endpoint (which can get ratelimited severely!) if ``fallback_from_bulk`` is True.

        Example for deleting all messages owned by the bot:

        .. code-block:: python3

            me = channel.guild.me
            await channel.purge(limit=100, author=me)

        Custom check functions can also be applied which specify any extra checks. They take one
        argument (the Message object) and return a boolean (True or False) determining if the
        message should be deleted.

        For example, to delete all messages with the letter ``i`` in them:

        .. code-block:: python3

            await channel.purge(limit=100, predicate=lambda message: 'i' in message.content)

        :param limit: The maximum amount of messages to delete. -1 for unbounded size.
        :param author: Only delete messages made by this author.
        :param content: Only delete messages that exactly match this content.
        :param predicate: A callable that determines if a message should be deleted.
        :param fallback_from_bulk: If this is True, messages will be regular deleted if they \
            cannot be bulk deleted.
        :return: The number of messages deleted.
        """
        return await self.messages.purge(limit=limit, author=author, content=content,
                                         predicate=predicate, fallback_from_bulk=fallback_from_bulk)

    async def send_typing(self) -> None:
        """
        Starts typing in the channel for 5 seconds.
        """
        if not self.type.has_messages():
            raise CuriousError("Cannot send messages to this channel")

        if self.guild:
            if not self.permissions(self.guild.me).send_messages:
                raise PermissionsError("send_message")

        await self._bot.http.send_typing(self.id)

    @property
    @asynccontextmanager
    @safe_generator
    async def typing(self) -> _typing.AsyncContextManager[None]:
        """
        :return: A context manager that sends typing repeatedly.

        Usage:

        .. code-block:: python3

            async with channel.typing:
                res = await do_long_action()

            await channel.messages.send("Long action:", res)
        """
        running = multio.Event()

        async def runner():
            await self.send_typing()
            while True:
                try:
                    async with multio.timeout_after(5):
                        await running.wait()
                except multio.asynclib.TaskTimeout:
                    await self.send_typing()
                else:
                    return

        async with multio.asynclib.task_manager() as tg:
            await multio.asynclib.spawn(tg, runner)
            try:
                yield
            finally:
                await multio.asynclib.cancel_task_group(tg)

    @deprecated(since="0.7.0", see_instead="Channel.messages.send", removal="0.10.0")
    async def send(self, content: str = None, *,
                   tts: bool = False, embed: Embed = None) -> 'dt_message.Message':
        """
        Sends a message to this channel.

        This requires SEND_MESSAGES permission in the channel.
        If the content is not a string, it will be automatically stringified.

        .. code:: python

            await channel.send("Hello, world!")

        :param content: The content of the message to send.
        :param tts: Should this message be text to speech?
        :param embed: An embed object to send with this message.
        :return: A new :class:`.Message` object.
        """
        return await self.messages.send(content, tts=tts, embed=embed)

    @deprecated(since="0.7.0", see_instead="Channel.messages.upload", removal="0.10.0")
    async def send_file(self, file_content: bytes, filename: str,
                        *, message_content: _typing.Optional[str] = None) -> 'dt_message.Message':
        """
        Uploads a message to this channel.

        This requires SEND_MESSAGES and ATTACH_FILES permission in the channel.

        .. code:: python

            with open("/tmp/emilia_best_girl.jpg", 'rb') as f:
                await channel.send_file(f.read(), "my_waifu.jpg")

        :param file_content: The bytes-like file content to upload.
            This **cannot** be a file-like object.
            
        :param filename: The filename of the file.
        :param message_content: Optional: Any extra content to be sent with the message.
        :return: The new :class:`.Message` created.
        """
        return await self.messages.upload(file_content, filename, message_content=message_content)

    @deprecated(since="0.7.0", see_instead="Channel.messages.upload", removal="0.10.0")
    async def upload_file(self, filename: str, *,
                          message_content: str = None) -> 'dt_message.Message':
        """
        A higher level interface to ``send_file``.

        This allows you to specify one of the following to upload:

            - A filename (str)
            - A file-like object
            - A path-like object

        This will open the file, read it in binary, and upload it to the channel.

        :param filename: The file to send, in the formats specified above.
        :param message_content: Any extra content to be sent with the message.
        :return: The new :class:`.Message` created.
        """
        return await self.messages.upload(fp=filename, filename=filename,
                                          message_content=message_content)

    async def change_overwrite(self, overwrite: 'dt_permissions.Overwrite'):
        """
        Changes an overwrite for this channel.

        This overwrite must be an instance of :class:`.Overwrite`.

        :param overwrite: The specific overwrite to use.
            If this is None, the overwrite will be deleted.
        """
        if not self.guild:
            raise PermissionsError("manage_roles")

        if not self.permissions(self.guild.me).manage_roles:
            raise PermissionsError("manage_roles")

        target = overwrite.target

        if isinstance(target, dt_member.Member):
            type_ = "member"
        else:
            type_ = "role"

        if overwrite is None:
            # Delete the overwrite instead.
            coro = self._bot.http.remove_overwrite(channel_id=self.id, target_id=target.id)

            async def _listener(before, after):
                if after.id != self.id:
                    return False

                # probably right /shrug
                return True
        else:
            coro = self._bot.http.edit_overwrite(self.id, target.id, type_,
                                                 allow=overwrite.allow.bitfield,
                                                 deny=overwrite.deny.bitfield)

            async def _listener(before, after):
                return after.id == self.id

        async with self._bot.events.wait_for_manager("channel_update", _listener):
            await coro

        return self

    async def edit(self, **kwargs) -> 'Channel':
        """
        Edits this channel.
        """
        if self.guild is None:
            raise CuriousError("Can only edit guild channels")

        if not self.permissions(self.guild.me).manage_channels:
            raise PermissionsError("manage_channels")

        if "type_" in kwargs:
            kwargs["type"] = kwargs["type_"]

        if "type" not in kwargs:
            kwargs["type"] = self.type

        if "parent" in kwargs:
            kwargs["parent_id"] = kwargs["parent"].id

        await self._bot.http.edit_channel(self.id, **kwargs)
        return self

    async def delete(self) -> 'Channel':
        """
        Deletes this channel.
        """
        if not self.permissions(self.guild.me).manage_channels:
            raise PermissionsError("manaqe_channels")

        await self._bot.http.delete_channel(self.id)
        return self

    async def connect(self):
        """
        Connects to voice in this channel.
        """
        if self.type != ChannelType.VOICE:
            raise CuriousError("Cannot connect to a text channel")

        return await self.guild.connect_to_voice(self)
