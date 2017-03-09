"""
Wrappers for Widget objects.

.. currentmodule:: curious.dataclasses.widget
"""
import typing
from types import MappingProxyType

from curious.dataclasses import channel as dt_channel, guild as dt_guild
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.status import Game, Status


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

        #: The :class:`~.WidgetGuild` for this channel.
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
        #: The :class:`~.User` object associated with this member.
        self.user = bot.state.make_user(user_dict)

        #: The :class:`~.WidgetGuild` object associated with this member.
        self.guild = guild

        #: The game associated with this member.
        game = kwargs.get("game")
        if game is None:
            game = {}
        self.game = Game(**game) if game else None

        #: The :class:`~.Status` associated with this member.
        self.status = Status(kwargs.get("status"))


class WidgetGuild(Dataclass):
    """
    Represents a limited subsection of a guild.
    """

    def __init__(self, bot, **kwargs):
        super().__init__(id=int(kwargs.get("id", 0)), cl=bot)

        #: The name of this guild.
        self.name = kwargs.get("name", "")

        #: A mapping of :class:`~.WidgetChannel` in this widget guild.
        self._channels = {}  # type: typing.MutableMapping[int, WidgetChannel]
        for channel in kwargs.get("channels", []):
            c = WidgetChannel(bot=self._bot, guild=self, **channel)
            self._channels[c.id] = c

        #: A mapping of :class:`~.WidgetMember` in this widget guild.
        self._members = {}
        for member in kwargs.get("members", []):
            m = WidgetMember(bot=self._bot, guild=self, kwargs=member)
            self._members[m.id] = m

    @property
    def channels(self) -> 'typing.Mapping[int, WidgetChannel]':
        """
        :return: A read-only mapping of :class:`~.WidgetChannel` representing the channels for this guild. 
        """
        return MappingProxyType(self._channels)

    @property
    def members(self) -> 'typing.Mapping[int, WidgetMember]':
        """
        :return: A read-only mapping of :class:`~.WidgetMember` representing the channels for this guild. 
        """
        return MappingProxyType(self._members)

    def __repr__(self):
        return "<WidgetGuild id={} members={} name='{}'>".format(self.id, len(self.members), self.name)

    __str__ = __repr__


class Widget(object):
    """
    Represents the embed widget for a guild.
    """

    def __init__(self, client, **kwargs):
        self._bot = client

        # we have a limited subsection of a full Guild object here
        id_ = int(kwargs.get("id", 0))

        # chekc to see if we have the real guild
        try:
            self._real_guild = client.guilds[id_]
        except KeyError:
            self._real_guild = None
            self._widget_guild = WidgetGuild(self._bot, **kwargs)
        else:
            self._widget_guild = None

        #: The invite URL that this widget represents.
        self.invite_url = kwargs.get("instant_invite", None)

    @property
    def guild(self) -> 'typing.Union[dt_guild.Guild, WidgetGuild]':
        """
        :return: The guild object associated with this widget. 
        :rtype: One of :class:`~.Guild`, :class:`~.WidgetGuild`.
        """
        return self._real_guild or self._widget_guild

    @property
    def channels(self) -> 'typing.Iterable[typing.Union[dt_channel.Channel, WidgetChannel]]':
        """
        :return: The channels associated with this widget. 
        :rtype: One of :class:`~.Channel`, :class:`~.WidgetChannel`.
        """
        return self.guild.channels

    def __repr__(self):
        return "<Widget guild={}>".format(self.guild)
