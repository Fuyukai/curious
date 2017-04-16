"""
Wrappers for voice state objects.

.. currentmodule:: curious.dataclasses.voice_state
"""
import typing

from curious.dataclasses import user as dt_user
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel


class VoiceState(object):
    """
    Represents the voice state of a user.
    """
    __slots__ = ("_user_id", "_guild_id", "_guild", "_channel_id", "_channel", "_self_mute",
                 "_server_mute", "_self_deaf", "_server_deaf")

    def __init__(self, **kwargs):
        self._user_id = int(kwargs.get("user_id", 0)) or None

        self._guild_id = int(kwargs.get("guild_id", 0)) or None

        #: The :class:`~.Guild` this voice state is associated with.
        self._guild = None

        self._channel_id = int(kwargs.get("channel_id", 0)) or None
        #: The voice channel this member is in.
        self._channel = None

        # Internal state values.
        self._self_mute = kwargs.get("self_mute", False)
        self._server_mute = kwargs.get("mute", False)
        self._self_deaf = kwargs.get("self_deaf", False)
        self._server_deaf = kwargs.get("deaf", False)

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`~.Guild` associated, or None if the guild is uncached.
        """
        if self._guild is None:
            return None

        return self._guild()

    @property
    def channel(self) -> 'dt_channel.Channel':
        """
        :return: The :class:`~.Channel` associated, or None if the channel is uncached.
        """
        if self._channel is None:
            return None

        return self._channel()

    @property
    def user(self) -> 'typing.Union[dt_user.User, None]':
        """
        :return: The :class:`~.User` associated with this VoiceState. 
        """
        try:
            return self.channel._bot.state._users.get(self._user_id)
        except AttributeError:
            return None

    def __del__(self):
        if not hasattr(self, "_channel") or not self._channel:
            return

        # decache if appropriate
        try:
            self.channel._bot.state._check_decache_user(self._user_id)
        except AttributeError:
            return None

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
        return "<VoiceState user={} deaf={} mute={} channel={}>".format(self.user, self.deafened,
                                                                        self.muted,
                                                                        self.channel)

    def mute(self):
        """
        Server mutes this member on the guild.
        """
        return self.guild.change_voice_state(self.member, mute=True)

    def unmute(self):
        """
        Server unmutes this member on the guild.
        """
        return self.guild.change_voice_state(self.member, mute=False)

    async def deafen(self):
        """
        Server deafens this member on the guild.
        """
        return self.guild.change_voice_state(self.member, deaf=True)

    async def undeafen(self):
        """
        Server undeafens this member on the guild.
        """
        return self.guild.change_voice_state(self.member, deaf=False)
