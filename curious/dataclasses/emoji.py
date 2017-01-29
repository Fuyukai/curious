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
        super().__init__(int(kwargs.pop("id")))

        #: The name of this emoji.
        self.name = kwargs.pop("name", None)

        # this is empty until it's filled up by our guild object
        #: The roles this emoji can be used by.
        self.roles = []  # type: typing.List[dt_role.Role]
        self._role_ids = kwargs.pop("roles", [])

        #: If this emoji requires colons to use.
        self.require_colons = kwargs.pop("require_colons", False)

        #: If this emoji is managed or not.
        self.managed = False

        #: The guild this emoji is associated with.
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
