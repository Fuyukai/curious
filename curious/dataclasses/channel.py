"""
Wrappers for Channel objects.

.. currentmodule:: curious.dataclasses.channel
"""
import collections
import enum
import pathlib
import sys
import time
import typing as _typing
from math import floor
from types import MappingProxyType

import curio

from curious.core import client as dt_client
from curious.dataclasses import guild as dt_guild, invite as dt_invite, member as dt_member, \
    message as dt_message, permissions as dt_permissions, role as dt_role, user as dt_user, \
    webhook as dt_webhook
from curious.dataclasses.bases import Dataclass, IDObject
from curious.dataclasses.embed import Embed
from curious.exc import CuriousError, Forbidden, PermissionsError
from curious.util import AsyncIteratorWrapper, base64ify

PY36 = sys.version_info[0:2] >= (3, 6)


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


class _TypingCtxManager:
    """
    A context manager that when entered, starts typing, and cancels when exited.
    
.. code-block:: python3
    
        async with ctx_man:
            await long_operation()
            ...
        
        print("done")
        
    This class should **not** be instantiated directly - instead, use :meth:`~.Channel.typing`.
    """

    def __init__(self, channel: 'Channel'):
        self._channel = channel

        self._t = None  # type: curio.Task

    async def __aenter__(self):
        self._t = await curio.spawn(self._type(), daemon=True)
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._t.cancel()

    async def _type(self):
        while True:
            await self._channel.send_typing()
            await curio.sleep(5)


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

    def __init__(self, channel: 'Channel', client: 'dt_client.Client',
                 max_messages: int = -1, *,
                 before: int = None, after: int = None):
        self.channel = channel
        self.client = client

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

    async def fill_messages(self):
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
            messages = await self.client.http.get_message_history(self.channel.id,
                                                                  before=self.last_message_id,
                                                                  limit=to_get)
        else:
            messages = await self.client.http.get_message_history(self.channel.id,
                                                                  after=self.last_message_id)
            messages = reversed(messages)

        for message in messages:
            self.messages.append(self.client.state.make_message(message))

    async def __anext__(self):
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

    def __iter__(self):
        raise RuntimeError("Use `async for`")

    def __await__(self):
        raise RuntimeError("This is not a coroutine")

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


class Channel(Dataclass):
    """
    Represents a channel object.
    """

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.get("id"), client)

        #: The name of this channel.
        self.name = kwargs.get("name", None)

        #: The topic of this channel.
        self.topic = kwargs.get("topic", None)

        #: The ID of the guild this is associated with.
        self.guild_id = int(kwargs.get("guild_id", 0)) or None

        parent_id = kwargs.get("parent_id")
        if parent_id is not None:
            parent_id = int(parent_id)

        #: The parent ID of this channel.
        self.parent_id = parent_id

        #: The :class:`~.ChannelType` of channel this channel is.
        self.type = ChannelType(kwargs.get("type", 0))

        #: If this channel is NSFW.
        self.nsfw: bool = kwargs.get("nsfw", False)

        #: If private, the list of :class:`~.User` that are in this channel.
        self._recipients = {}
        if self.private:
            for recipient in kwargs.get("recipients", []):
                u = self._bot.state.make_user(recipient)
                self._recipients[u.id] = u

            if self.type == ChannelType.GROUP:
                # append the current user
                self._recipients[self._bot.user.id] = self._bot.user

        #: The position of this channel.
        self.position = kwargs.get("position", 0)

        #: The last message ID of this channel.
        #: Used for history.
        _last_message_id = kwargs.get("last_message_id", 0)
        if _last_message_id:
            self._last_message_id = int(_last_message_id)
        else:
            self._last_message_id = None

        # group channel stuff
        #: The owner ID of the channel.
        #: This is None for non-group channels.
        self.owner_id = int(kwargs.get("owner_id", 0)) or None

        #: The icon hash of the channel.
        self.icon_hash = kwargs.get("icon", None)

        #: The internal overwrites for this channel.
        self._overwrites = {}

    def __repr__(self):
        return f"<Channel id={self.id} name={self.name} type={self.type.name} " \
               f"guild_id={self.guild_id}>"

    __str__ = __repr__

    def _update_overwrites(self, overwrites: list, guild=None):
        self._overwrites = {}

        guild = self.guild or guild

        for overwrite in overwrites:
            id = int(overwrite["id"])
            type_ = overwrite["type"]

            if type_ == "member":
                obb = guild._members.get(id)
            else:
                obb = guild._members.get(id)

            self._overwrites[id] = dt_permissions.Overwrite(allow=overwrite["allow"],
                                                            deny=overwrite["deny"],
                                                            obb=obb, channel=self)

    @property
    def guild(self) -> '_typing.Union[dt_guild.Guild, None]':
        """
        :return: The :class:`~.Guild` associated with this Channel.
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
        :return: A mapping of int -> :class:`~.User` for the recipients of this private chat.
        """
        return MappingProxyType(self._recipients)

    @property
    def user(self) -> '_typing.Union[dt_user.User, None]':
        """
        :return: If this channel is a private channel, the :class:`~.User` of the other user.
        """
        if self.type != ChannelType.PRIVATE:
            return None

        return list(self.recipients.values())[0]

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
    def history(self) -> HistoryIterator:
        """
        :return: A :class:`~.AsyncIteratorWrapper: that can be used to iterate over the last \
            infinity messages.
        """
        return self.get_history(before=self._last_message_id, limit=-1)

    @property
    def pins(self) -> '_typing.AsyncIterator[dt_message.Message]':
        """
        :return: A :class:`~.AsyncIteratorWrapper` that can be used to iterate over the pins. 
        """
        return AsyncIteratorWrapper(self.get_pins())

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
            raise RuntimeError("No members for channels that aren't voice channels")

        return list(
            filter(lambda member: member.voice.channel == self, self.guild.members.values())
        )

    def permissions(self, obb: '_typing.Union[dt_member.Member, dt_role.Role]') -> \
            'dt_permissions.Overwrite':
        """
        Gets the permission overwrites for the specified object.
        """
        overwrite = self._overwrites.get(obb.id)
        if not overwrite:
            return dt_permissions.Overwrite(0, 0, obb, channel=self)

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

    def get_history(self, before: int = None,
                    after: int = None,
                    limit: int = 100) -> HistoryIterator:
        """
        Gets history for this channel.

        This is *not* a coroutine - it returns a :class:`HistoryIterator` which can be async 
        iterated over to get message history.

        .. code-block:: python3
        
            async for message in channel.get_history(limit=1000):
                print(message.content, "by", message.author.user.name)

        :param limit: The maximum number of messages to get.
        :param before: The snowflake ID to get messages before.
        :param after: The snowflake ID to get messages after.
        """
        if self.guild:
            if not self.permissions(self.guild.me).read_message_history:
                raise PermissionsError("read_message_history")

        return HistoryIterator(self, self._bot, before=before, after=after, max_messages=limit)

    async def get_pins(self) -> '_typing.List[dt_message.Message]':
        """
        Gets the pins for a channel.

        :return: A list of :class:`~.Message` objects.
        """
        msg_data = await self._bot.http.get_pins(self.id)

        messages = []
        for message in msg_data:
            messages.append(self._bot.state.make_message(message))

        return messages

    async def get_webhooks(self) -> '_typing.List[dt_webhook.Webhook]':
        """
        Gets the webhooks for this channel.

        :return: A list of :class:`~.Webhook` objects for the channel.
        """
        webhooks = await self._bot.http.get_webhooks_for_channel(self.id)
        obbs = []

        for webhook in webhooks:
            obbs.append(self._bot.state.make_webhook(webhook))

        return obbs

    async def get_message(self, message_id: int) -> 'dt_message.Message':
        """
        Gets a single message from this channel.

        :param message_id: The message ID to retrieve.
        :return: A new :class:`.Message` object.
        """
        if self.guild:
            if not self.permissions(self.guild.me).read_message_history:
                raise PermissionsError("read_message_history")

        if self._bot.user.bot:
            data = await self._bot.http.get_message(self.id, message_id)
        else:
            data = await self._bot.http.get_message_history(self.id, around=message_id, limit=1)
            if not data:
                raise CuriousError("No messages found for this ID")
            else:
                data = data[0]

        msg = self._bot.state.make_message(data)

        return msg

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
        webhook._default_name = data.get("name")
        webhook._default_avatar = data.get("avatar")

        webhook.user.username = data.get("name")
        webhook.user.avatar_hash = data.get("avatar")

        return webhook

    async def delete_webhook(self, webhook: 'dt_webhook.Webhook') -> 'dt_webhook.Webhook':
        """
        Deletes a webhook.

        You must have MANAGE_WEBHOOKS to delete this webhook.

        :param webhook: The :class:`~.Webhook` to delete.
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

        :param messages: A list of :class:`~.Message` objects to delete.
        :return: The number of messages deleted.
        """
        if self.guild:
            if not self.permissions(self.guild.me).manage_messages:
                raise PermissionsError("manage_messages")

        minimum_allowed = floor((time.time() - 14 * 24 * 60 * 60) * 1000.0 - 1420070400000) << 22
        ids = []
        for message in messages:
            if message.id < minimum_allowed:
                raise CuriousError("Cannot delete messages older than {}".format(minimum_allowed))
            ids.append(message.id)

        await self._bot.http.delete_multiple_messages(self.id, ids)

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
        if self.guild:
            if not self.permissions(self.guild.me).manage_messages and not fallback_from_bulk:
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
        for chunk in message_chunks:
            m = floor((time.time() - 14 * 24 * 60 * 60) * 1000.0 - 1420070400000) << 22
            message_ids = []
            for message in chunk:
                if message.id < m:
                    raise CuriousError("Cannot delete messages older than {}".format(m))
                message_ids.append(message.id)
            # First, try and bulk delete all the messages.
            if can_bulk_delete:
                try:
                    await self._bot.http.delete_multiple_messages(self.id, message_ids)
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

    async def send_typing(self) -> None:
        """
        Starts typing in the channel for 5 seconds.
        """
        if self.type == ChannelType.VOICE:
            raise CuriousError("Cannot send messages to a voice channel")

        if self.guild:
            if not self.permissions(self.guild.me).send_messages:
                raise PermissionsError("send_message")

        await self._bot.http.send_typing(self.id)

    @property
    def typing(self):
        """
        :return: A context manager that sends typing repeatedly.
        """
        return _TypingCtxManager(self)

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
        :return: A new :class:`~.Message` object.
        """
        if self.type not in [ChannelType.TEXT, ChannelType.PRIVATE]:
            raise CuriousError("Cannot send messages to a voice channel")

        if self.guild:
            if not self.permissions(self.guild.me).send_messages:
                raise PermissionsError("send_messages")

        if not isinstance(content, str) and content is not None:
            content = str(content)

        # check for empty messages
        if not content:
            if not embed:
                raise CuriousError("Cannot send an empty message")

            if self.guild and not self.permissions(self.guild.me).embed_links:
                raise PermissionsError("embed_links")
        else:
            if content and len(content) > 2000:
                raise CuriousError("Content must be less than 2000 characters")

        if embed is not None:
            embed = embed.to_dict()

        data = await self._bot.http.send_message(self.id, content, tts=tts, embed=embed)
        obb = self._bot.state.make_message(data, cache=True)

        return obb

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
        :return: The new :class:`~.Message` created.
        """
        if self.type == ChannelType.VOICE:
            raise CuriousError("Cannot send messages to a voice channel")

        if self.guild:
            if not self.permissions(self.guild.me).send_messages:
                raise PermissionsError("send_messages")

            if not self.permissions(self.guild.me).attach_files:
                raise PermissionsError("attach_files")

        data = await self._bot.http.send_file(self.id, file_content,
                                              filename=filename, content=message_content)
        obb = self._bot.state.make_message(data, cache=False)
        return obb

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
        :return: The new :class:`~.Message` created.
        """
        if self.type == ChannelType.VOICE:
            raise CuriousError("Cannot send messages to a voice channel")

        if self.guild:
            if not self.permissions(self.guild.me).send_messages:
                raise PermissionsError("send_messages")

            if not self.permissions(self.guild.me).attach_files:
                raise PermissionsError("attach_files")

        if hasattr(filename, "read"):
            # file-like
            file_data = filename.read()
            name = getattr(filename, "name", None)
        else:
            # assume it's pathlike
            path = pathlib.Path(filename)
            name = path.parts[-1]

            if not PY36:
                # open() on python 3.6+ supports pathlike objects, so no need to stringify the path.
                # however, we're on 3.5, so stringify it now.
                path = str(path)

            with open(path, mode='rb') as f:
                file_data = f.read()

        return await self.send_file(file_data, name, message_content=message_content)

    async def change_overwrite(self, overwrite: 'dt_permissions.Overwrite'):
        """
        Changes an overwrite for this channel.

        This overwrite must be an instance of :class:`~.Overwrite`.

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

            listener = await curio.spawn(self._bot.wait_for("channel_update", _listener))
        else:
            coro = self._bot.http.edit_overwrite(self.id, target.id, type_,
                                                 allow=overwrite.allow.bitfield,
                                                 deny=overwrite.deny.bitfield)

            async def _listener(before, after):
                return after.id == self.id

            listener = await curio.spawn(self._bot.wait_for("channel_update", _listener))

        try:
            await coro
        except:
            await listener.cancel()
            raise
        await listener.join()
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
            kwargs["type"] = ChannelType.TEXT

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
