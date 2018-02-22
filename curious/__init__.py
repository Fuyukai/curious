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
Curious - An async Python 3.6+ library for Discord bots.

.. currentmodule:: curious

.. autosummary::
    :toctree: 
    
    core
    commands
    dataclasses
    ext.paginator
    
    exc
    util
"""
from __future__ import generator_stop  # enforce generator stop

import sys

from pkg_resources import DistributionNotFound, get_distribution

try:
    __version__ = get_distribution("discord-curious").version
except DistributionNotFound:
    __version__ = "0.0.0"

_fmt = "DiscordBot (https://github.com/SunDwarf/curious {0}) Python/{1[0]}.{1[1]}"
USER_AGENT = _fmt.format(__version__, sys.version_info)
del _fmt


from curious.core.client import BotType, Client
from curious.core.event import EventContext, event
from curious.core.gateway import open_websocket, GatewayHandler
from curious.core.state import GuildStore, State
from curious.dataclasses.appinfo import AppInfo
from curious.dataclasses.attachment import Attachment
from curious.dataclasses.bases import Dataclass, IDObject
from curious.dataclasses.channel import Channel, ChannelType
from curious.dataclasses.embed import Embed
from curious.dataclasses.emoji import Emoji
from curious.dataclasses.guild import ContentFilterLevel, Guild, GuildChannelWrapper, \
    GuildEmojiWrapper, GuildRoleWrapper, MFALevel, NotificationLevel, VerificationLevel
from curious.dataclasses.invite import Invite, InviteChannel, InviteGuild, InviteMetadata
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.presence import Game, Presence, Status
from curious.dataclasses.reaction import Reaction
from curious.dataclasses.role import Role
from curious.dataclasses.search import SearchQuery, SearchResults
from curious.dataclasses.user import User
from curious.dataclasses.voice_state import VoiceState
from curious.dataclasses.webhook import Webhook
from curious.dataclasses.widget import Widget, WidgetChannel, WidgetGuild, WidgetMember

# for asks
# import multio
# multio.init('curio')
