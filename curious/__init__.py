"""
Curious - A Curio-based Python 3.5+ library for Discord bots.

.. currentmodule:: curious

.. autosummary::
    :toctree: 
    
    core
    commands
    dataclasses
    http
    ext.loapi
    ext.paginator
    voice
    
    exc
    util
"""

from curious.core.client import BotType, Client
from curious.core.event import EventContext, event
from curious.core.gateway import Gateway
from curious.core.state import GuildStore, State
from curious.dataclasses.appinfo import AppInfo
from curious.dataclasses.bases import Dataclass, IDObject
from curious.dataclasses.channel import Channel, ChannelType
from curious.dataclasses.embed import Attachment, Embed
from curious.dataclasses.emoji import Emoji
from curious.dataclasses.guild import ContentFilterLevel, Guild, GuildChannelWrapper, \
    GuildRoleWrapper, MFALevel, NotificationLevel, VerificationLevel
from curious.dataclasses.invite import Invite, InviteChannel, InviteGuild, InviteMetadata
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.permissions import Overwrite, Permissions
from curious.dataclasses.presence import Game, Presence
from curious.dataclasses.reaction import Reaction
from curious.dataclasses.role import Role
from curious.dataclasses.search import SearchQuery, SearchResults
from curious.dataclasses.user import BotUser, User, UserProfile, UserSettings
from curious.dataclasses.voice_state import VoiceState
from curious.dataclasses.webhook import Webhook
from curious.dataclasses.widget import Widget, WidgetChannel, WidgetGuild, WidgetMember

__version__ = "0.5.0"
