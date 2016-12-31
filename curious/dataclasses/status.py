import enum


class Status(enum.Enum):
    ONLINE = 'online'
    OFFLINE = 'offline'
    IDLE = 'idle'
    DND = 'dnd'

    #: This will never be returned as a status.
    INVISIBLE = 'invisible'


class Game(object):
    """
    Represents a game object.
    """

    def __init__(self, **kwargs):
        self.type = kwargs.pop("type", None)
        self.url = kwargs.pop("url", None)
        self.name = kwargs.pop("name", None)

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
