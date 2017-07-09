"""
Wrappers for Status objects.

.. currentmodule:: curious.dataclasses.presence
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
        """
        :return: The strength of the presence, when computing the final presence on multiple \ 
            connections. 
        """
        return strengths.index(self)


strengths = [Status.OFFLINE, Status.INVISIBLE, Status.IDLE, Status.DND, Status.ONLINE]


class Game(object):
    """
    Represents a game object.
    """

    __slots__ = "type", "url", "name"

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


class Presence(object):
    """
    Represents a presence on a member.
    """

    __slots__ = "_status", "_game"

    def __init__(self, **kwargs):
        #: The :class:`~.Status` for this presence.
        self._status = None  # type: Status
        # prevent dupe code by using our setter
        self.status = kwargs.get("status", Status.OFFLINE)

        game = kwargs.get("game", None)
        #: The :class:`~.Game` for this presence.
        self._game = None  # type: Game

        # NB: this does a property set to ensure the types are right.
        self.game = game

    def __repr__(self):
        return "<Presence status={} game='{}'>".format(self.status, self.game)

    @property
    def status(self) -> Status:
        """
        :return: The :class:`~.Status` associated with this presence. 
        """
        return self._status

    @status.setter
    def status(self, value):
        if value is None:
            return

        if not isinstance(value, Status):
            value = Status(value)

        self._status = value

    @property
    def game(self) -> Game:
        """
        :return: The :class:`~.Game` associated with this presence.
        """
        return self._game

    @game.setter
    def game(self, value):
        if value is None:
            self._game = None
            return

        if not isinstance(value, Game):
            value = Game(**value)

        self._game = value

    @property
    def strength(self) -> int:
        """
        :return: The strength for this status.
        """
        return self.status.strength
