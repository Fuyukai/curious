"""
Wrappers for custom emojis in guilds.

.. currentmodule:: curious.dataclasses.emoji
"""

import typing

from curious.dataclasses.bases import IDObject
from curious.dataclasses import role as dt_role
from curious.dataclasses import guild as dt_guild


class Emoji(IDObject):
    """
    Represents a custom emoji uploaded to a guild.

    :ivar id: The ID of this emoji.
    """
    __slots__ = ("id", "name", "roles", "_role_ids", "require_colons", "managed", "guild")

    def __init__(self, **kwargs):
        super().__init__(int(kwargs.get("id")))

        #: The name of this emoji.
        self.name = kwargs.get("name", None)

        # this is empty until it's filled up by our guild object
        #: The list of :class:`~.Role` this emoji can be used by.
        self.roles = []  # type: typing.List[dt_role.Role]
        self._role_ids = kwargs.get("roles", [])

        #: If this emoji requires colons to use.
        self.require_colons = kwargs.get("require_colons", False)

        #: If this emoji is managed or not.
        self.managed = False

        #: The :class:`~.Guild` this emoji is associated with.
        self.guild = None  # type: dt_guild.Guild

    def __eq__(self, other):
        if isinstance(other, str):
            return False

        return self.id == other.id

    def __str__(self):
        return "<:{}:{}>".format(self.name, self.id)

    def __repr__(self):
        return "<Emoji guild={} id={}>".format(self.guild, self.id)

    @property
    def url(self) -> str:
        """
        :return: The URL to this emoji.
        """
        return "https://cdn.discordapp.com/emojis/{}.png".format(self.id)
