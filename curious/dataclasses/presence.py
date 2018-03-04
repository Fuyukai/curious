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
Wrappers for Status objects.

.. currentmodule:: curious.dataclasses.presence
"""

import enum
from typing import List


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


class GameType(enum.IntEnum):
    """
    Represents a game's type.
    """
    #: Shows the ``Playing`` text.
    PLAYING = 0

    #: Shows the ``Streaming`` text.
    STREAMING = 1

    #: Shows the ``Listening to`` text.
    LISTENING_TO = 2

    #: Shows the ``Watching`` text.
    WATCHING = 3


class Game(object):
    """
    Represents a game object.
    """

    __slots__ = "type", "url", "name"

    def __init__(self, **kwargs) -> None:
        """
        :param name: The name for the game. 100 characters max.
        :param url: The URL for the game, if streaming.
        :param type: A :class:`.GameType` for this game.
        """
        #: The type of game this is.
        self.type = GameType.PLAYING  # type: GameType
        try:
            self.type = GameType(kwargs.get("type", 0))
        except ValueError:
            self.type = kwargs.get("type", 0)

        #: The stream URL this game is for.
        self.url = kwargs.get("url", None)  # type: str
        #: The name of the game being played.
        self.name = kwargs.get("name", None)  # type: str

    def to_dict(self) -> dict:
        """
        :return: The dict representation of this object. 
        """
        d = {
            "name": self.name,
            "type": self.type,
        }
        if self.url is not None:
            d["url"] = self.url

        return d

    def __repr__(self) -> str:
        return "<Game name='{}' type={} url={}>".format(self.name, self.type, self.url)


class Presence(object):
    """
    Represents a presence on a member.
    """

    __slots__ = "_status", "_game"

    def __init__(self, **kwargs) -> None:
        """
        :param status: The :class:`.Status` for this presence.
        :param game: The :class:`.Game` for this presence.
        """
        #: The :class:~.Status` for this presence.
        self._status = None  # type: Status
        # prevent dupe code by using our setter
        self.status = kwargs.get("status", Status.OFFLINE)

        game = kwargs.get("game", None)
        #: The :class:`.Game` for this presence.
        self._game = None  # type: Game

        # NB: this does a property set to ensure the types are right.
        self.game = game

    def __repr__(self):
        return "<Presence status={} game='{}'>".format(self.status, self.game)

    @property
    def status(self) -> Status:
        """
        :return: The :class:`.Status` associated with this presence.
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
        :return: The :class:`.Game` associated with this presence.
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


def _make_property(field: str, doc: str = None, max_size: int = None) -> property:
    def _getter(self):
        return self._rich_fields.get(field)

    def _setter(self, value: str):
        if max_size is not None and len(value) > max_size:
            raise ValueError("Field '{}' cannot be longer than {} characters"
                             .format(field, max_size))

        self._rich_fields[field] = value

    prop = property(_getter, _setter, doc=doc)
    return prop


class RichPresence(object):
    """
    Represents a Rich Presence. This class can be created safely for usage with :class:`.IPCClient`.
    """

    # typedef struct DiscordRichPresence {
    #     const char* state; /* max 128 bytes */
    #     const char* details; /* max 128 bytes */
    #     int64_t startTimestamp;
    #     int64_t endTimestamp;
    #     const char* largeImageKey; /* max 32 bytes */
    #     const char* largeImageText; /* max 128 bytes */
    #     const char* smallImageKey; /* max 32 bytes */
    #     const char* smallImageText; /* max 128 bytes */
    #     const char* partyId; /* max 128 bytes */
    #     int partySize;
    #     int partyMax;
    #     const char* matchSecret; /* max 128 bytes */
    #     const char* joinSecret; /* max 128 bytes */
    #     const char* spectateSecret; /* max 128 bytes */
    #     int8_t instance;
    # } DiscordRichPresence;
    def __init__(self, **fields):
        """
        :param fields: The rich presence fields.
        """
        self._rich_fields = fields

    state = _make_property("state", "The state for this presence.", 128)
    details = _make_property("details", "The details for this presence.", 128)

    @property
    def assets(self) -> dict:
        """
        The assets for this rich presence. Returns a dict of
        (large_image, large_text, small_image, small_text).
        """
        return self._rich_fields.get("assets", {})

    @assets.setter
    def assets(self, value: dict):
        for key in value.keys():
            if key not in ('large_image', 'large_text', 'small_image', 'small_text'):
                raise ValueError("Bad asset key: {}".format(key))

        self._rich_fields["assets"] = value

    @property
    def party_id(self) -> str:
        """
        The party ID for this rich presence.
        """
        return self._rich_fields.get("party", {}).get("id")

    @party_id.setter
    def party_id(self, value):
        if "party" not in self._rich_fields:
            self._rich_fields["party"] = {"id": value}
        else:
            self._rich_fields["party"]["id"] = value

    @property
    def party_size(self) -> List[int]:
        """
        The size of the party for this rich presence. An array of [size, max].
        """
        return self._rich_fields.get("party", {}).get("size")

    @party_size.setter
    def party_size(self, size: List[int]):
        if "party" not in self._rich_fields:
            self._rich_fields["party"] = {"size": size}
        else:
            self._rich_fields["party"]["size"] = size

