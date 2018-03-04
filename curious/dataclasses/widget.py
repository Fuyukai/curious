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
Wrappers for Widget objects.

.. currentmodule:: curious.dataclasses.widget
"""
import typing
from types import MappingProxyType

from curious.dataclasses import channel as dt_channel, guild as dt_guild
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.presence import Game, Status


class WidgetChannel(Dataclass):
    """
    Represents a limited subsection of a channel.
    """

    def __init__(self, bot, guild: 'WidgetGuild', **kwargs):
        super().__init__(id=int(kwargs.get("id", 0)), cl=bot)

        #: The name of this channel.
        self.name = kwargs.get("name")

        #: The position of this channel.
        self.position = kwargs.get("position", -1)

        #: The guild ID for this channel.
        self.guild_id = guild.id

        #: The :class:`.WidgetGuild` for this channel.
        self.guild = guild


class WidgetMember(Dataclass):
    """
    Represents a limited subsection of a member.
    """

    def __init__(self, bot, guild: 'WidgetGuild', kwargs):
        super().__init__(id=int(kwargs.get("id", 0)), cl=bot)

        # construct a superficial user dict
        user_dict = {
            "id": self.id,
            "name": kwargs.get("name", None),
            "avatar": kwargs.get("avatar", None),
            "discriminator": kwargs.get("discriminator", None),
            "bot": kwargs.get("bot", False)
        }
        #: The :class:`.User` object associated with this member.
        self.user = bot.state.make_user(user_dict)
        bot.state._check_decache_user(user_dict["id"])

        #: The :class:`.WidgetGuild` object associated with this member.
        self.guild = guild

        #: The game associated with this member.
        game = kwargs.get("game")
        if game is None:
            game = {}
        self.game = Game(**game) if game else None

        #: The :class:`.Status` associated with this member.
        self.status = Status(kwargs.get("status"))


class WidgetGuild(Dataclass):
    """
    Represents a limited subsection of a guild.
    """

    def __init__(self, bot, **kwargs):
        super().__init__(id=int(kwargs.get("id", 0)), cl=bot)

        #: The name of this guild.
        self.name = kwargs.get("name", "")

        #: A mapping of :class:`.WidgetChannel` in this widget guild.
        self._channels = {}  # type: typing.MutableMapping[int, WidgetChannel]
        for channel in kwargs.get("channels", []):
            c = WidgetChannel(bot=self._bot, guild=self, **channel)
            self._channels[c.id] = c

        #: A mapping of :class:`.WidgetMember` in this widget guild.
        self._members = {}
        for member in kwargs.get("members", []):
            m = WidgetMember(bot=self._bot, guild=self, kwargs=member)
            self._members[m.id] = m

    @property
    def channels(self) -> 'typing.Mapping[int, WidgetChannel]':
        """
        :return: A read-only mapping of :class:`.WidgetChannel` representing the channels for \
            this guild. 
        """
        return MappingProxyType(self._channels)

    @property
    def members(self) -> 'typing.Mapping[int, WidgetMember]':
        """
        :return: A read-only mapping of :class:`.WidgetMember` representing the channels for \
            this guild. 
        """
        return MappingProxyType(self._members)

    def __repr__(self):
        return "<WidgetGuild id={} members={} name='{}'>".format(self.id, len(self.members),
                                                                 self.name)

    __str__ = __repr__


class Widget(object):
    """
    Represents the embed widget for a guild.
    """

    def __init__(self, client, **kwargs):
        self._bot = client

        #: The guild ID for this widget.
        self.guild_id = int(kwargs.get("id", 0))

        #: The widget guild for this widget.
        self._widget_guild = WidgetGuild(self._bot, **kwargs)

        #: The invite URL that this widget represents.
        self.invite_url = kwargs.get("instant_invite", None)

    @property
    def guild(self) -> 'typing.Union[dt_guild.Guild, WidgetGuild]':
        """
        :return: The guild object associated with this widget.
            If the guild was cached, a :class:`.Guild`. Otherwise, a :class:`.WidgetGuild`.
        """
        try:
            return self._bot.guilds[self.guild_id]
        except KeyError:
            return self._widget_guild

    @property
    def channels(self) -> 'typing.Mapping[int, typing.Union[dt_channel.Channel, WidgetChannel]]':
        """
        :return: A mapping of channels associated with this widget.
        """
        return self.guild.channels

    def __repr__(self):
        return "<Widget guild={}>".format(self.guild)
