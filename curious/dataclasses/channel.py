import collections
import enum

from curious import client as dt_client
from curious.dataclasses import guild as dt_guild
from curious.dataclasses.bases import Dataclass

from curious.dataclasses import message as dt_message
from curious.dataclasses import user as dt_user


class ChannelType(enum.Enum):
    TEXT = 0
    PRIVATE = 1
    VOICE = 2


class HistoryIterator(collections.AsyncIterator):
    """
    Returned from the `history` to iterate over history.
    """

    def __init__(self, channel: 'Channel', client: 'dt_client.Client',
                 max_messages: int=-1, *,
                 before: int=None, after: int=None):
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

        #: The message ID of after to fetch.
        self.after = after

        #: The last message ID that we fetched.
        if self.before:
            self.last_message_id = self.before
        else:
            self.last_message_id = self.after

    async def _fill_messages(self):
        """
        Called to fill the next <n> messages.
        """
        if self.max_messages < 0:
            to_get = 100
        else:
            to_get = self.max_messages - self.current_count

        if self.before:
            messages = await self.client.http.get_messages(self.channel.id, before=self.last_message_id,
                                                           limit=to_get)
        else:
            messages = await self.client.http.get_messages(self.channel.id, after=self.last_message_id)
            messages = reversed(messages)

        for message in messages:
            self.messages.append(self.client.state.parse_message(message))

    async def __anext__(self):
        self.current_count += 1
        if self.current_count == self.max_messages:
            raise StopAsyncIteration

        if len(self.messages) <= 0:
            await self._fill_messages()

        try:
            message = self.messages.popleft()
        except IndexError:
            # No messages to fill, so self._fill_messages didn't return any
            # This signals the end of iteration.
            raise StopAsyncIteration
        self.last_message_id = message.id

        return message


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

        #: If it is private, the recipients of the channel.
        self.recipients = []
        if self.is_private:
            for recipient in kwargs.pop("recipients"):
                self.recipients.append(dt_user.User(self._bot, **recipient))

        #: The position of this channel.
        self.position = kwargs.pop("position", 0)

        #: The last message ID of this channel.
        #: Used for history.
        self._last_message_id = int(kwargs.pop("last_message_id", 0))

    @property
    def is_private(self):
        return self.type not in [ChannelType.TEXT, ChannelType.VOICE]

    @property
    def user(self):
        """
        :return: If this channel is a private channel, return the user of the channel.
        """
        if self.type != ChannelType.PRIVATE:
            return None

        return self.recipients[0]

    @property
    def history(self) -> HistoryIterator:
        return self.get_history(before=self._last_message_id, limit=-1)

    def _copy(self):
        obb = object.__new__(self.__class__)
        obb.name = self.name
        obb.type = self.type
        obb.guild = self.guild
        obb.recipients = self.recipients
        obb.position = self.position
        obb._bot = self._bot
        return obb

    def get_history(self, before: int=None,
                    after: int=None,
                    limit: int=100) -> HistoryIterator:
        """
        Gets history for this channel.

        This is *not* a coroutine - it returns a :class:`HistoryIterator` which can be async iterated over to get
        message history.

        :param limit: The maximum number of messages to get.
        :param before: The snowflake ID to get messages before.
        :param after: The snowflake ID to get messages after.
        """
        return HistoryIterator(self, self._bot, before=before, after=after, max_messages=limit)

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

        data = await self._bot.http.send_message(self.id, content, tts=tts)
        obb = self._bot.state.parse_message(data, cache=False)

        return obb
