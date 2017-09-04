"""
Wrappers for custom emojis in guilds.

.. currentmodule:: curious.dataclasses.emoji
"""

import typing

from curious.dataclasses import guild as dt_guild, role as dt_role
from curious.dataclasses.bases import Dataclass


class Emoji(Dataclass):
    """
    Represents a custom emoji uploaded to a guild.
    """
    __slots__ = ("id", "name", "role_ids", "require_colons", "managed", "guild_id")

    def __init__(self, **kwargs):
        super().__init__(int(kwargs.get("id")), kwargs.get("client"))

        #: The name of this emoji.
        self.name = kwargs.get("name", None)

        #: A list of role IDs that this emoji can be used by.
        self.role_ids = kwargs.get("roles", [])

        #: If this emoji requires colons to use.
        self.require_colons: bool = kwargs.get("require_colons", False)

        #: If this emoji is managed or not.
        self.managed: bool = False

        #: The ID of the guild this emoji is associated with.
        self.guild_id: int = None

    def __eq__(self, other):
        if isinstance(other, str):
            return False

        return self.id == other.id

    def __str__(self):
        return "<:{}:{}>".format(self.name, self.id)

    def __repr__(self):
        return "<Emoji guild={} id={}>".format(self.guild, self.id)

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`.Guild` this emoji object is associated with.
        """
        return self._bot.guilds.get(self.guild_id)

    @property
    def roles(self) -> 'typing.List[dt_role.Role]':
        """
        :return: A list of :class:`.Role` this emoji can be used by.
        """
        if len(self.role_ids) <= 0:
            return [self.guild.default_role]

        return [self.guild.roles[r_id] for r_id in self.role_ids]

    @property
    def url(self) -> str:
        """
        :return: The URL to this emoji.
        """
        return "https://cdn.discordapp.com/emojis/{}.png".format(self.id)
