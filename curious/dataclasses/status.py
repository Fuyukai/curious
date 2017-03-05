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


class Game(object):
    """
    Represents a game object.
    """

    def __init__(self, **kwargs):
        self.type = kwargs.get("type", None)
        self.url = kwargs.get("url", None)
        self.name = kwargs.get("name", None)

    def to_dict(self):
        d = {
            "name": self.name
        }
        if self.type == 1:
            d["type"] = 1
            d["url"] = self.url

        return d

    def __repr__(self):
        return "<Game name={}>".format(self.name)
