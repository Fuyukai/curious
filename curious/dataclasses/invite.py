import typing

from curious import util
from curious import client
from curious.dataclasses import guild as dt_guild, channel as dt_channel
from curious.dataclasses.bases import IDObject


class InviteGuild(IDObject):
    """
    Represents an InviteGuild - a subset of a guild.
    """

    def __init__(self, **kwargs):
        super().__init__(kwargs.pop("id"))

        #: The name of this guild.
        self.name = kwargs.pop("name", None)  # type: str

        #: The splash hash of this guild.
        self._splash_hash = kwargs.get("splash")  # type: str

        #: The icon hash of this guild.
        self._icon_hash = kwargs.get("icon")  # type: str

    def __repr__(self):
        return "<InviteGuild id={} name='{}'>".format(self.id, self.name)

    __str__ = __repr__

    @property
    def icon_url(self) -> str:
        """
        :return: The icon URL for this guild, or None if one isn't set.
        """
        if self._icon_hash:
            return "https://cdn.discordapp.com/icons/{}/{}.webp".format(self.id, self._icon_hash)

    @property
    def splash_url(self) -> str:
        """
        :return: The splash URL for this guild, or None if one isn't set.
        """
        if self._splash_hash:
            return "https://cdn.discordapp.com/splashes/{}/{}.webp".format(self.id, self._splash_hash)


class InviteChannel(IDObject):
    """
    Represents an InviteChannel - a subset of a channel.
    """

    def __init__(self, **kwargs):
        super().__init__(kwargs.pop("id"))

        #: The name of this channel.
        self.name = kwargs.pop("name")

        #: The type of this channel.
        self.type = dt_channel.ChannelType(kwargs.pop("type"))

    def __repr__(self):
        return "<InviteChannel name={}>".format(self.name)


class InviteMetadata(object):
    """
    Represents metadata attached to an invite.
    """

    __slots__ = "uses", "max_uses", "max_age", "temporary", "created_at", "revoked",

    def __init__(self, **kwargs):
        #: The number of times this invite was used.
        self.uses = kwargs.pop("uses", 0)  # type: int

        #: The maximum number of uses this invite can use.
        self.max_uses = kwargs.pop("max_uses", 0)  # type: int

        #: The maximum age of this invite.
        self.max_age = kwargs.pop("max_age", 0)  # type: int

        #: Is this invite temporary?
        self.temporary = kwargs.pop("temporary", False)  # type: bool

        #: When was this invite created at?
        self.created_at = util.to_datetime(kwargs.pop("created_at", None))

        #: Is this invite revoked?
        self.revoked = kwargs.pop("revoked", False)  # type: bool


class Invite(object):
    """
    Represents an invite object.
    """

    __slots__ = "_bot", "code", "_real_guild", "_real_channel", "_invite_guild", "_invite_channel", "_invite_metadata"

    def __init__(self, client: 'client.Client', **kwargs):
        self._bot = client

        #: The invite code.
        self.code = kwargs.get("code")  # type: str

        guild_id = int(kwargs["guild"]["id"])
        # check to see if it's in our state first, failing that construct an InviteGuild object.
        if guild_id in client.state._guilds:
            self._real_guild = client.state._guilds[guild_id]
            self._real_channel = self._real_guild._channels[int(kwargs["channel"]["id"])]
        else:
            self._real_guild = None
            self._real_channel = None

        # The invite guild this is attached to.
        # The actual guild object can be more easily fetched with `.guild`.
        self._invite_guild = InviteGuild(**kwargs.pop("guild"))

        # The invite channel this is attached to.
        # The actual channel object can be more easily fetched with `.channel`.
        self._invite_channel = InviteChannel(**kwargs.pop("channel"))

        #: The invite metadata object associated with this invite.
        #: This can be None if the invite has no metadata.
        if "uses" not in kwargs:
            self._invite_metadata = None
        else:
            self._invite_metadata = InviteMetadata(**kwargs)

    def __repr__(self):
        return "<Invite code={} guild={} channel={}>".format(self.code, self.guild, self.channel)

    @property
    def guild(self) -> 'typing.Union[dt_guild.Guild, InviteGuild]':
        """
        :return: The guild this invite is associated with.
        """
        return self._real_guild or self._invite_guild

    @property
    def channel(self) -> 'typing.Union[dt_channel.Channel, InviteChannel]':
        """
        :return: The channel this invite is associated with.
        """
        return self._real_channel or self._invite_channel

    async def delete(self):
        """
        Deletes this invite.

        You must have MANAGE_CHANNELS permission in the guild to delete the invite.
        """
        await self._bot.http.delete_invite(self.code)
