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
    def __init__(self, **kwargs):
        #: The :class:`Message` this reaction is for.
        self.message = None

        #: The emoji that represents this reaction.
        self.emoji = None  # type: typing.Union[str, dt_emoji.Emoji]

        #: The number of times this message was reacted to.
        self.count = kwargs.get("count", 1)  # 1 is better than 0

        #: If this user reacted to the message.
        self.me = kwargs.get("me", False)

    def __repr__(self):
        return "<Reaction emoji={} count={}>".format(self.emoji, self.count)

    def __eq__(self, other):
        if not isinstance(other, Reaction):
            return NotImplemented

        if self.message.id != other.message.id:
            return NotImplemented

        return self.emoji == other.emoji

    def __hash__(self):
        # naiive
        return hash(self.message) + hash(self.emoji)
