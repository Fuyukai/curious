"""
Wrappers for voice state objects.

.. currentmodule:: curious.dataclasses.voice_state
"""

from curious.dataclasses import user as dt_user
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel


class VoiceState(object):
    """
    Represents the voice state of a user.
    """
    __slots__ = ("_user_id", "user", "_guild_id", "guild", "_channel_id", "channel", "_self_mute", "_server_mute",
                 "_self_deaf", "_server_deaf")

    def __init__(self, user: 'dt_user.User', **kwargs):
        self._user_id = int(kwargs.get("user_id", 0)) or None
        #: The user object this voice state is for.
        self.user = user

        self._guild_id = int(kwargs.get("guild_id", 0)) or None

        #: The guild this voice state is associated with.
        self.guild = None  # type: dt_guild.Guild

        self._channel_id = int(kwargs.get("channel_id", 0)) or None
        #: The voice channel this member is in.
        self.channel = None  # type: dt_channel.Channel

        # Internal state values.
        self._self_mute = kwargs.get("self_mute", False)
        self._server_mute = kwargs.get("mute", False)
        self._self_deaf = kwargs.get("self_deaf", False)
        self._server_deaf = kwargs.get("deaf", False)

    @property
    def muted(self) -> bool:
        """
        :return: If this user is muted or not.
        """
        return self._server_mute or self._self_mute

    @property
    def deafened(self) -> bool:
        """
        :return: If this user is deafened or not.
        """
        return self._server_deaf or self._self_deaf

    @property
    def member(self):
        """
        :return: The member this is associated with.
        """
        return self.guild.members[int(self._user_id)]

    def __repr__(self):
        return "<VoiceState user={} deaf={} mute={} channel={}>".format(self.user, self.deafened, self.muted,
                                                                        self.channel)

    async def mute(self):
        """
        Server mutes this member on the guild.
        """
        await self.guild.change_voice_state(self.member, mute=True)

    async def unmute(self):
        """
        Server unmutes this member on the guild.
        """
        await self.guild.change_voice_state(self.member, mute=False)

    async def deafen(self):
        """
        Server deafens this member on the guild.
        """
        await self.guild.change_voice_state(self.member, deaf=True)

    async def undeafen(self):
        """
        Server undeafens this member on the guild.
        """
        await self.guild.change_voice_state(self.member, deaf=False)
