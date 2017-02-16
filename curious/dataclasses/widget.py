import typing
from types import MappingProxyType

from curious.dataclasses import channel as dt_channel, guild as dt_guild
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.status import Game, Status


class WidgetChannel(Dataclass):
    """
    Represents a limited subsection of a channel.
    """

    def __init__(self, bot: 'client.Client', guild: 'WidgetGuild', **kwargs):
        super().__init__(id=int(kwargs.get("id", 0)), client=bot)

        #: The name of this channel.
        self.name = kwargs.pop("name")

        #: The position of this channel.
        self.position = kwargs.pop("position", -1)

        #: The guild ID for this channel.
        self.guild_id = guild.id

        #: The WidgetGuild for this channel.
        self.guild = guild


class WidgetMember(Dataclass):
    """
    Represents a limited subsection of a member.
    """

    def __init__(self, bot: 'client.Client', guild: 'WidgetGuild', kwargs):
        super().__init__(id=int(kwargs.get("id", 0)), client=bot)

        # construct a superficial user dict
        user_dict = {
            "id": self.id,
            "name": kwargs.get("name", None),
            "avatar": kwargs.get("avatar", None),
            "discriminator": kwargs.get("discriminator", None),
            "bot": kwargs.get("bot", False)
        }
        #: The user object associated with this member.
        self.user = bot.state.make_user(user_dict)

        #: The game associated with this member.
        game = kwargs.get("game")
        if game is None:
            game = {}
        self.game = Game(**game) if game else None

        #: The status associated with this member.
        self.status = Status(kwargs.get("status"))


class WidgetGuild(Dataclass):
    """
    Represents a limited subsection of a guild.
    """

    def __init__(self, bot: 'client.Client', **kwargs):
        super().__init__(id=int(kwargs.get("id", 0)), client=bot)

        #: The name of this guild.
        self.name = kwargs.pop("name", "")

        #: The channels in this widget guild.
        self._channels = {}  # type: typing.List[WidgetChannel]
        for channel in kwargs.get("channels", []):
            c = WidgetChannel(bot=self._bot, guild=self, **channel)
            self._channels[c.id] = c

        #: The members in this widget guild.
        self._members = {}
        for member in kwargs.get("members", []):
            m = WidgetMember(bot=self._bot, guild=self, kwargs=member)
            self._members[m.id] = m

    @property
    def channels(self):
        return MappingProxyType(self._channels)

    @property
    def members(self):
        return MappingProxyType(self._members)

    def __repr__(self):
        return "<WidgetGuild id={} members={} name='{}'>".format(self.id, len(self.members), self.name)

    __str__ = __repr__

class Widget(object):
    """
    Represents the embed widget for a guild.
    """

    def __init__(self, client: 'client.Client', **kwargs):
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

        self.invite_url = kwargs.get("instant_invite", None)

    @property
    def guild(self) -> 'typing.Union[dt_guild.Guild, WidgetGuild]':
        """
        :return: The guild object associated with this widget. 
        """
        return self._real_guild or self._widget_guild

    @property
    def channels(self) -> 'typing.Iterable[typing.Union[dt_channel.Channel, WidgetChannel]]':
        return self.guild.channels

    def __repr__(self):
        return "<Widget guild={}>".format(self.guild)
