"""
Wrappers for Application Info objects.

.. currentmodule:: curious.dataclasses.appinfo
"""
from collections import namedtuple

from curious.exc import CuriousError
from curious.dataclasses import guild as dt_guild

AuthorizedApp = namedtuple("AuthorizedApp", "scopes id application")


class AppInfo(object):
    """
    Represents the application info for an OAuth2 application.
    """

    def __init__(self, client, **kwargs):
        self._bot = client

        self._application = kwargs.get("application", {})

        #: The client ID of this application.
        self.client_id = int(self._application.get("id", 0))

        #: The owner of this application.
        #: This can be None if the application fetched isn't the bot's.
        if "owner" in self._application:
            self.owner = self._bot.state.make_user(self._application.get("owner"))
        else:
            self.owner = None

        #: The name of this application.
        self.name = self._application.get("name", None)  # type: str

        #: The description of this application.
        self.description = self._application.get("description", None)  # type: str

        #: Is this bot public?
        self.public = self._application.get("bot_public", None)  # type: bool

        #: Does this bot require OAuth2 Code Grant?
        self.requires_code_grant = self._application.get("bot_require_code_grant", None)  # type: bool

        #: The icon hash for this application.
        self._icon_hash = self._application.get("icon", None)  # type: str

        if "bot" in kwargs:
            #: The bot :class:`~.User` associated with this application.
            self.bot = self._bot.state.make_user(kwargs.get("bot", {}))  # type: User
        else:
            self.bot = None

    def __repr__(self):
        return "<AppInfo owner='{}' name='{}' bot='{}'>".format(self.owner, self.name, self.bot)

    @property
    def icon_url(self):
        """
        :return: The icon url for this bot.
        """
        if self._icon_hash is None:
            return None

        return "https://cdn.discordapp.com/app-icons/{}/{}.jpg".format(self.client_id, self._icon_hash)

    async def add_to_guild(self, guild: 'dt_guild.Guild', *,
                           permissions: int=0):
        """
        Authorizes this bot to join a guild.

        This requires a userbot client to be used.
        """
        if self._bot.is_bot:
            raise CuriousError("Bots cannot add other bots")

        if self.bot is None:
            raise CuriousError("This application has no bot associated")

        if self.owner is None and not self.public:
            raise CuriousError("This bot is not public")

        if self.requires_code_grant:
            raise CuriousError("This bot requires code grant")

        await self._bot.http.authorize_bot(self.client_id, guild.id, permissions=permissions)
