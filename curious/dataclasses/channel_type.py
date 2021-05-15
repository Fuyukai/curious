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
Stores the enumeration for Discord channel types.

.. currentmodule:: curious.dataclasses.channel
"""

from __future__ import annotations

import enum


class ChannelType(enum.IntEnum):
    """
    Returns a mapping from Discord channel type.
    """

    #: A regular guild text channel.
    GUILD_TEXT = 0

    #: A private channel, such as a DM.
    DM = 1

    #: A regular guild voice channel.
    GUILD_VOICE = 2

    #: A group chat.
    GROUP_DM = 3

    #: A category channel; a parent of other channels.
    GUILD_CATEGORY = 4

    #: A news channel that users can follow.
    GUILD_NEWS = 5

    #: A store channel for selling games.
    GUILD_STORE = 6

    #: A temporary subchannel within a news channel.
    GUILD_NEWS_THREAD = 10

    #: A temporary subchannel within a text channel.
    GUILD_PUBLIC_THREAD = 11

    GUILD_PRIVATE_THREAD = 12

    GUILD_STAGE_VOICE = 13

    def has_messages(self) -> bool:
        """
        :return: If this channel type has messages.
        """
        return self not in (
            ChannelType.GUILD_VOICE,
            ChannelType.GUILD_CATEGORY,
            ChannelType.GUILD_STAGE_VOICE,
        )
