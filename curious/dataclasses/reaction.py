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
Wrappers for Reaction objects.

.. currentmodule:: curious.dataclasses.reaction
"""

import typing

from curious.dataclasses import emoji as dt_emoji


class Reaction(object):
    """
    Represents a reaction.
    """
    def __init__(self, **kwargs) -> None:
        #: The :class:`.Message` this reaction is for.
        self.message = None

        #: The emoji that represents this reaction.
        self.emoji = None  # type: typing.Union[str, dt_emoji.Emoji]

        #: The number of times this message was reacted to.
        self.count = kwargs.get("count", 1)  # 1 is better than 0

        #: If this user reacted to the message.
        self.me = kwargs.get("me", False)

    def __repr__(self) -> str:
        return "<Reaction emoji={} count={}>".format(self.emoji, self.count)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Reaction):
            return NotImplemented

        if self.message.id != other.message.id:
            return NotImplemented

        return self.emoji == other.emoji

    def __hash__(self) -> int:
        # naiive
        return hash(self.message) + hash(self.emoji)
