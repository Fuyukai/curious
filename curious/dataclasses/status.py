"""
Wrappers for Status objects.

.. currentmodule:: curious.dataclasses.status
"""

import enum


class Status(enum.Enum):
    """
    Represents a Member's status.
    """
    #: Corresponds to online (green dot).
    ONLINE = 'online'

    #: Corresponds to offline (gray dot).
    OFFLINE = 'offline'

    #: Corresponds to idle (yellow dot).
    IDLE = 'idle'

    #: Corresponds to Do Not Disturb (red dot).
    DND = 'dnd'

    #: Corresponds to invisible (gray dot).
    INVISIBLE = 'invisible'

    @property
    def strength(self) -> int:
        return strengths.index(self)


strengths = [Status.OFFLINE, Status.INVISIBLE, Status.IDLE, Status.DND, Status.ONLINE]


class Game(object):
    """
    Represents a game object.
    """

    def __init__(self, **kwargs):
        #: The type of game this is.
        self.type = kwargs.get("type", 0)
        #: The stream URL this game is for.
        self.url = kwargs.get("url", None)
        #: The name of the game being played.
        self.name = kwargs.get("name", None)

    def to_dict(self) -> dict:
        """
        :return: The dict representation of this object. 
        """
        d = {
            "name": self.name
        }
        if self.type == 1:
            d["type"] = 1
            d["url"] = self.url

        return d

    def __repr__(self):
        return "<Game name='{}' type={} url={}>".format(self.name, self.type, self.url)
