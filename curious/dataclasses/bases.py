"""
Base classes.
"""
import abc
import datetime

from curious import client

DISCORD_EPOCH = 1420070400000


class Messagable(abc.ABC):
    @abc.abstractmethod
    async def send(self, content: str=None, *, tts: bool=False, embed=None):
        """
        Send a message to the target.

        :param content: The content to return.
        :param tts: Is this message a text to speech message?
        :param embed: The embed to send instead of a message.
        :return: A new :class:`Message` representing the message returned.
        """


class IDObject(object):
    """
    This object is comparable using the snowflake as an ID.

    It is also hashable, using the ID as a hash.
    """

    def __init__(self, id: int):
        """
        :param id: The snowflake ID of the object.
        """
        if isinstance(id, str):
            id = int(id)

        self.id = id

    def __repr__(self):
        return "<{} id={}>".format(self.__class__.__name__, self.id)

    __str__ = __repr__

    @property
    def timestamp(self):
        """
        :return: The timestamp of the snowflake.
        """
        return datetime.datetime.utcfromtimestamp(((int(self.id) >> 22) + DISCORD_EPOCH) / 1000)

    def __eq__(self, other):
        return other.id == self.id

    def __hash__(self):
        return self.id


class Dataclass(IDObject):
    """
    The base class for all dataclasses.

    These contain a reference to the current bot as `_bot`.
    """

    def __init__(self, id: int, client: 'client.Client'):
        super().__init__(id)

        self._bot = client
