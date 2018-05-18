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
Wrappers for voice state objects.

.. currentmodule:: curious.dataclasses.voice_state
"""

from curious.dataclasses import channel as dt_channel, guild as dt_guild, member as dt_member


class VoiceState(object):
    """
    Represents the voice state of a user.
    """
    __slots__ = ("user_id", "guild_id", "channel_id", "_self_mute",
                 "_server_mute", "_self_deaf", "_server_deaf", "_bot")

    def __init__(self, **kwargs) -> None:
        self._bot = kwargs.get("client")

        #: The ID of the user for this VoiceState.
        self.user_id = int(kwargs.get("user_id", 0)) or None

        #: The ID of the guild for this VoiceState.
        self.guild_id = int(kwargs.get("guild_id", 0)) or None

        #: The ID of the channel for this VoiceState.
        self.channel_id = int(kwargs.get("channel_id", 0)) or None

        # Internal state values.
        self._self_mute = kwargs.get("self_mute", False)
        self._server_mute = kwargs.get("mute", False)
        self._self_deaf = kwargs.get("self_deaf", False)
        self._server_deaf = kwargs.get("deaf", False)

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`.Guild` associated, or None if the guild is uncached.
        """
        return self._bot.guilds.get(self.guild_id)

    @property
    def channel(self) -> 'dt_channel.Channel':
        """
        :return: The :class:`.Channel` associated, or None if the channel is uncached.
        """
        return self.guild.channels.get(self.channel_id)

    @property
    def member(self) -> 'dt_member.Member':
        """
        :return: The :class:`.Member` associated, or None.
        """
        return self.guild.members.get(self.user_id)

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

    def __repr__(self):
        return "<VoiceState user={} deaf={} mute={} channel={}>".format(self.member.user,
                                                                        self.deafened,
                                                                        self.muted,
                                                                        self.channel)

    async def mute(self):
        """
        Server mutes this member on the guild.
        """
        return await self.guild.change_voice_state(self.member, mute=True)

    async def unmute(self):
        """
        Server unmutes this member on the guild.
        """
        return await self.guild.change_voice_state(self.member, mute=False)

    async def deafen(self):
        """
        Server deafens this member on the guild.
        """
        return await self.guild.change_voice_state(self.member, deaf=True)

    async def undeafen(self):
        """
        Server undeafens this member on the guild.
        """
        return await self.guild.change_voice_state(self.member, deaf=False)

    async def move(self, to_channel: 'dt_channel.Channel'):
        """
        Moves a user to a different voice channel.
        """
        return await self.guild.change_voice_state(self.member, channel=to_channel)