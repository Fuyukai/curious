"""
Base classes.
"""
import datetime

from curious import client

DISCORD_EPOCH = 1420070400000


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

    @property
    def timestamp(self):
        """
        :return: The timestamp of the snowflake.
        """
        return datetime.datetime.utcfromtimestamp(((int(id) >> 22) + DISCORD_EPOCH) / 1000)

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
