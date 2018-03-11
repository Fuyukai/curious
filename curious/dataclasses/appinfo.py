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
Wrappers for Application Info objects.

.. currentmodule:: curious.dataclasses.appinfo
"""
from typing import Union

from curious.dataclasses import user as dt_user
from curious.dataclasses.bases import Dataclass


class AppInfo(Dataclass):
    """
    Represents the application info for an OAuth2 application.
    """

    def __init__(self, client, **kwargs) -> None:
        self._application = kwargs.get("application", {})

        #: The client ID of this application.
        self.client_id = int(self._application.get("id", 0))
        super().__init__(self.client_id, client)

        if "owner" in self._application:
            owner = self._bot.state.make_user(self._application.get("owner"))
        else:
            owner = None

        #: The owner of this application.
        #: This can be None if the application fetched isn't the bot's.
        self.owner = owner

        #: The name of this application.
        self.name = self._application.get("name", None)  # type: str

        #: The description of this application.
        self.description = self._application.get("description", None)  # type: str

        #: Is this bot public?
        self.public = self._application.get("bot_public", None)  # type: bool

        #: Does this bot require OAuth2 Code Grant?
        self.requires_code_grant = self._application.get("bot_require_code_grant",
                                                         None)  # type: bool

        #: The icon hash for this application.
        self._icon_hash = self._application.get("icon", None)  # type: str

        #: The bot :class:`.User` associated with this application, if available.
        self.bot = None  # type: dt_user.User

        if "bot" in kwargs:
            self.bot = self._bot.state.make_user(kwargs.get("bot", {}))
        else:
            self.bot = None

    def __repr__(self) -> str:
        return "<{} owner='{!r}' name='{!r}' bot='{!r}'>".format(type(self).__name__, self.owner,
                                                                 self.name, self.bot)

    @property
    def icon_url(self) -> Union[str, None]:
        """
        :return: The icon url for this bot.
        """
        if self._icon_hash is None:
            return None

        return "https://cdn.discordapp.com/app-icons/{}/{}.jpg".format(self.client_id,
                                                                       self._icon_hash)

