"""
Defines :class:`~.State`.

.. currentmodule:: curious.core.state
"""

import collections
import copy
import logging
import typing
from types import MappingProxyType

import curio

from curious.core import gateway
from curious.dataclasses.channel import Channel, ChannelType
from curious.dataclasses.emoji import Emoji
from curious.dataclasses.guild import ContentFilterLevel, Guild, MFALevel, NotificationLevel, \
    VerificationLevel
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.permissions import Permissions
from curious.dataclasses.presence import Presence, Status
from curious.dataclasses.reaction import Reaction
from curious.dataclasses.role import Role
from curious.dataclasses.user import BotUser, FriendType, RelationshipUser, User, UserSettings
from curious.dataclasses.voice_state import VoiceState
from curious.dataclasses.webhook import Webhook

UserType = typing.TypeVar("U", bound=User)
logger = logging.getLogger("curious.state")


def int_or_none(val, default: typing.Any) -> typing.Union[int, None]:
    """
    Returns int or None.
    """
    if val is None:
        return default

    return int(val)


class GuildStore(collections.MutableMapping):
    """
    A store for guilds in the state.
    """

    def __init__(self):
        #: The internal actual guilds.
        self.guilds = {}

        #: The order of the guilds, as specified by the READY packet.
        self.order = []

    def view(self) -> typing.Mapping[int, Guild]:
        """
        :return: A :class:`mappingproxy` of the internal guilds. 
        """
        return MappingProxyType(self.guilds)

    @property
    def with_order(self) -> 'typing.Mapping[int, Guild]':
        """
        :return: A mapping of the guilds with the order specified in the ready packet.
        """
        if not self.order:
            return self.view()

        o = collections.OrderedDict()
        for guild in map(int, self.order):
            o[guild] = self.guilds[guild]

        return MappingProxyType(o)

    # abc methods
    def __setitem__(self, key, value):
        return self.guilds.__setitem__(key, value)

    def __getitem__(self, key):
        return self.guilds.__getitem__(key)

    def __delitem__(self, key):
        return self.guilds.__delitem__(key)

    def __iter__(self):
        return self.guilds.__iter__()

    def __len__(self):
        return self.guilds.__len__()


class State(object):
    """
    This represents the state of the Client - in other libraries, the cache.

    It is also used to parse objects into their representations.
    """

    def __init__(self, client, max_messages: int = 500):
        #: The current user of this bot.
        #: This is automatically set after login.
        self._user = None  # type: BotUser

        #: The client associated with this connection.
        self.client = client

        #: The private channel cache.
        self._private_channels = {}

        #: The guilds the bot can see.
        self._guilds = GuildStore()

        #: This user's friends.
        self._friends = {}  # type: typing.Dict[int, RelationshipUser]

        #: This user's blocked users.
        self._blocked = {}  # type: typing.Dict[int, RelationshipUser]

        #: The current user cache.
        self._users = {}

        #: The state logger.
        logger = logging.getLogger("curious.state")

        #: The deque of messages.
        #: This is bounded to prevent the message cache from growing infinitely.
        self._messages = collections.deque(maxlen=max_messages)

        self.__shards_is_ready = collections.defaultdict(lambda *args, **kwargs: curio.Event())
        self.__voice_state_crap = collections.defaultdict(
            lambda *args, **kwargs: ((curio.Event(), curio.Event()), {})
        )

    def is_ready(self, shard_id: int) -> curio.Event:
        """
        Checks if a shard is ready.
        
        :param shard_id: The shard ID to check.
        :return: A :class:`curio.Event` signifying if this shard is ready or not.
        """
        return self.__shards_is_ready[shard_id]

    def _reset(self, shard_id: int):
        """
        Called after session is invalidated, to reset our state.
        """
        self.__shards_is_ready.pop(shard_id, None)

        for guild in self.guilds_for_shard(shard_id):
            guild._finished_chunking.clear()

    def _mark_for_chunking(self, gw: 'gateway.Gateway', guild: Guild):
        """
        Marks a guild for chunking.
        """
        if all(not g.unavailable for g in self.guilds_for_shard(guild.shard_id)):
            gw._enqueued_guilds.append(guild)
            # we have all guilds anyway, so raise ChunkGuilds NOW
            raise gateway.ChunkGuilds

        if len(gw._enqueued_guilds) >= 74:
            # bump it up to 75, if applicable
            gw._enqueued_guilds.append(guild)
            raise gateway.ChunkGuilds

        gw._enqueued_guilds.append(guild)

    @property
    def guilds(self) -> typing.Mapping[int, Guild]:
        """
        :return: A mapping of int -> :class:`.Guild`.
        """
        return self._guilds.view()

    @property
    def guilds_ordered(self) -> typing.Mapping[int, Guild]:
        """
        :return: An ordered mapping of int -> :class:`.Guild` by the user's guild ordering.
        """
        return self._guilds.with_order

    def have_all_chunks(self, shard_id: int):
        """
        Checks if we have all the chunks for the specified shard.

        :param shard_id: The shard ID to check.
        """
        if any(guild.unavailable is True for guild in self.guilds.values()):
            return False

        return all(guild._finished_chunking.is_set()
                   for guild in self.guilds.values()
                   if guild.shard_id == shard_id and guild.unavailable is False)

    def guilds_for_shard(self, shard_id: int):
        """
        Gets all the guilds for a particular shard.
        """
        return [guild for guild in self.guilds.values() if guild.shard_id == shard_id]

    async def _check_ready(self, gw: 'gateway.Gateway', guild: Guild):
        """
        Checks if we should dispatch ready for this shard.
        """
        if self.is_ready(gw.shard_id).is_set():
            # Already ready, don't bother.
            return

        if self.have_all_chunks(gw.shard_id):
            # Have all chunks anyway, dispatch now.
            logger.info(
                "All guilds fully chunked on shard {}, dispatching READY.".format(gw.shard_id)
            )
            await self.is_ready(gw.shard_id).set()
            await self.client.fire_event("ready", gateway=gw)

            # check for userbots
            if not self._user.bot:
                # request a guild sync
                logger.info("Requesting GUILD_SYNC to update our presences.")
                await gw.send_guild_sync(self.guilds.values())

            return

        if self._user.bot:
            # Check if we need to forcibly fire ChunkGuilds.
            if all(g.unavailable is False for g in self.guilds_for_shard(gw.shard_id)):
                raise gateway.ChunkGuilds

    # get_all_* methods
    def get_all_channels(self) -> typing.Generator[Channel, None, None]:
        """
        :return: A generator that yields all :class:`~.Channel`s the bot can see.
        """
        for guild in self._guilds.values():
            for channel in guild.channels.values():
                yield channel

    def get_all_members(self) -> typing.Generator[Member, None, None]:
        """
        :return: A generator that yields all :class:`~.Member`s the bot can see.
        """
        for guild in self.guilds.values():
            for member in guild.members.values():
                yield member

    def get_all_roles(self) -> typing.Generator[Role, None, None]:
        """
        :return: A generator that yields all :class:`~.Role`s the bot can see. 
        """
        for guild in self.guilds.values():
            for role in guild.roles.values():
                yield role

    def find_channel(self, channel_id: int) -> typing.Union[Channel, None]:
        """
        Finds a channel by ID.  
        This will search all guild channels, as well as private channels.
        
        :param channel_id: The ID of the channel to find.
        :return: A :class:`~.Channel` that represents the channel, or None if no channel was found.
        """
        # default channel_id == guild id
        # for old guilds with a default channel
        if channel_id in self._guilds:
            try:
                return self._guilds[channel_id].channels[channel_id]
            except KeyError:
                return None

        if channel_id in self._private_channels:
            return self._private_channels[channel_id]

        for guild in self._guilds.values():
            if channel_id in guild._channels:
                return guild._channels[channel_id]

    def _find_message(self, message_id: int) -> Message:
        for message in reversed(self._messages):
            if message.id == message_id:
                return message

    def _check_decache_user(self, id: int):
        """
        Checks if we should decache a user.

        This will check if there is any guild with a reference to the user.
        """
        # don't check if its not there
        if id not in self._users:
            return

        # don't decache ourself
        if self._users[id] == self._user:
            return

        # if its in friends/blocked, keep the RelationshipUser
        if id in self._friends or id in self._blocked:
            return

        # check if its in a private channel
        for channel in self._private_channels.values():
            if id in channel.recipients:
                return

        # check if it's any guilds
        for guild in self._guilds.values():
            if id in guild.members:
                return

        # didn't return, so no references
        self._users.pop(id, None)

    # make_ methods
    def make_webhook(self, event_data: dict) -> Webhook:
        """
        Creates a new webhook object from the event data.

        :param event_data: The event data.
        :return: A :class:`~.Webhook`.
        """
        if "content" in event_data:
            # message object, so we have to do a minor bit of remapping
            user = event_data.get("author", {})
            webhook_id = int(event_data.pop("webhook_id", 0))
            owner = {}
        else:
            # make a "fake" user
            webhook_id = int(event_data.get("id", 0))
            user = {
                "id": webhook_id,
                "discriminator": "0000",
                "avatar": event_data.get("avatar"),
                "username": event_data.get("username")
            }
            owner = event_data.get("user", {})

        channel = self.find_channel(int(event_data.get("channel_id")))
        user = self.make_user(user)
        # ensure the webhook user is decached
        self._check_decache_user(user.id)
        user.bot = True
        webhook = Webhook(client=self.client, webhook_id=webhook_id, **event_data)
        webhook.guild_id = channel.guild_id
        webhook.channel_id = channel.id
        webhook.user = user
        webhook.token = event_data.get("token", None)

        if owner:
            # only create Owner if the data was returned
            webhook.owner = self.make_user(owner)
            self._check_decache_user(webhook.owner.id)

        # default fields, these are lazily loaded by properties
        webhook._default_name = event_data.get("name", None)
        webhook._default_avatar = event_data.get("avatar", None)

        return webhook

    def make_private_channel(self, channel_data: dict) -> Channel:
        """
        Creates a new private channel and caches it.

        :param channel_data: The channel data to cache.
        :return: A new :class:`~.Channel`.
        """
        channel = Channel(self.client, **channel_data)
        self._private_channels[channel.id] = channel

        return channel

    def make_user(self, user_data: dict, *,
                  user_klass: typing.Type[UserType] = User,
                  override_cache: bool = False) -> UserType:
        """
        Creates a new user and caches it.

        :param user_data: The user data to use to create.
        :param user_klass: The type of user to create.
        :param override_cache: Should the cache be overridden?
        :return: A new :class`~.User` (hopefully).
        """
        id = int(user_data.get("id", 0))
        if id in self._users and not override_cache:
            return self._users[id]

        user = user_klass(self.client, **user_data)
        self._users[user.id] = user

        return user

    def make_message(self, event_data: dict, cache: bool = True) -> Message:
        """
        Constructs a new message object.
        
        :param event_data: The message data to use to create.
        :param cache: Should this message be cached?
        :return: A new :class:`~.Message` object for the message.
        """
        message = Message(self.client, **event_data)

        if message in self._messages:
            # don't bother re-caching
            i = self._messages.index(message)
            return self._messages[i]

        # discord won't give us the Guild id
        # so we have to search it from the channels
        channel_id = int(event_data.get("channel_id", 0))
        channel = self.find_channel(channel_id)

        author_id = int(event_data.get("author", {}).get("id", 0))

        message.channel = channel
        if channel is not None:
            message.guild_id = channel.guild_id
        if message.channel.type == ChannelType.PRIVATE:
            if author_id == self._user.id:
                message.author = self._user
            else:
                message.author = message.channel.user
        elif message.channel.type == ChannelType.GROUP:
            message.author = message.channel.recipients.get(author_id, None)
        else:
            # Webhooks also exist.
            if event_data.get("webhook_id") is not None:
                message.author = self.make_webhook(event_data)
            else:
                message.author = message.guild.members.get(author_id)

        for reaction_data in event_data.get("reactions", []):
            emoji = reaction_data.get("emoji", {})
            reaction = Reaction(**reaction_data)

            if "id" in emoji and emoji["id"] is not None:
                emoji_obb = message.guild.emojis.get(int(emoji["id"]))
                if emoji_obb is None:
                    emoji_obb = Emoji(id=emoji["id"], name=emoji["name"])
            else:
                emoji_obb = emoji.get("name", None)

            reaction.emoji = emoji_obb
            message.reactions.append(reaction)

        if cache and message not in self._messages:
            self._messages.append(message)

        return message

    async def wait_for_voice_data(self, guild_id: int):
        """
        Waits for the two voice data packets to be received for the specified guild.
        """
        events, state = self.__voice_state_crap[guild_id]  # state is a pointer

        for event in events:
            await event.wait()

        # pop out the event data for laeter reconnects
        self.__voice_state_crap.pop(guild_id)

        return state

    # Event handlers.
    # These parse the events and deconstruct them.
    async def handle_ready(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when READY is dispatched.
        """
        gw.session_id = event_data.get("session_id")

        # Create our bot user.
        self._user = BotUser(self.client, **event_data.get("user"))
        # cache ourselves
        self._users[self._user.id] = self._user

        logger.info(
            "We have been issued a session on shard {}, parsing ready for `{}#{}` ({})"
                .format(gw.shard_id, self._user.username, self._user.discriminator, self._user.id)
        )

        logger.info("Logged in as a userbot: {}".format(not self._user.bot))

        # User-bots only.
        # Parse relationships first before processing anything else.
        # This ensures all friends are calculated and assigned.
        if not self._user.bot:
            # Parse settings.
            settings = event_data.get("user_settings", {})
            self._user.settings = UserSettings(self.client, **settings)
            self._user.settings.status = event_data.get("status", None)

            # Parse friends and blocked users.
            for item in event_data.get("relationships", []):
                # make user to cache it
                user = self.make_user(item.get("user", {}), user_klass=RelationshipUser)
                user.type_ = FriendType(item["type"])
                if user.type_ == FriendType.FRIEND:
                    self._friends[int(item["id"])] = user
                else:
                    self._blocked[int(item["id"])] = user

            for presence in event_data.get("presences", []):
                try:
                    u = int(presence["user"]["id"])
                except KeyError:
                    # what the fuck?!?!?
                    logger.warning("Got None user for presence. What?")
                    continue
                fr = self._friends.get(u)

                # eventual consistency
                if not fr:
                    continue

                fr.presence = Presence(**presence)

            self._guilds.order = list(map(int, self._user.settings.guild_positions))

            logger.info("Processed {} friends "
                        "and {} blocked users.".format(len(self._friends), len(self._blocked)))

        # Create all of the guilds.
        for guild in event_data.get("guilds", []):
            new_guild = Guild(self.client, **guild)
            new_guild.shard_id = gw.shard_id
            self._guilds[new_guild.id] = new_guild

            if not self._user.bot and len(event_data.get("guilds")) <= 100:
                # this might as well be a GUILD_CREATE, so treat it as one
                new_guild.start_chunking()
                await self.handle_guild_create(gw, guild)
                gw._dispatches_handled["GUILD_CREATE"] += 1

        if not self._user.bot and len(event_data.get("guilds")) <= 100:
            # Chunk now, sync later.
            await gw.request_chunks([g for g in self.guilds.values()])
            logger.info("Chunking {} guilds immediately.".format(len(self.guilds)))

        logger.info("Ready processed for shard {}. Delaying until all guilds are chunked."
                    .format(gw.shard_id))

        # Don't fire `_ready` here, because we don't have all guilds.
        await self.client.fire_event("connect", gateway=gw)

        # event_data.pop("guilds")
        # pprint.pprint(event_data)

        # However, if the client has no guilds, we DO want to fire ready.
        if len(event_data.get("guilds", {})) == 0:
            await self.is_ready(gw.shard_id).set()
            logger.info("No more guilds to get for shard {}, or client is user. "
                        "Dispatching READY.".format(gw.shard_id))
            await self.client.fire_event("ready", gateway=gw)

    async def handle_resumed(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when the gateway connection is resumed.
        """
        prev_seq = gw._prev_seq
        gw._prev_seq = gw.sequence_num
        new_events = gw.sequence_num - prev_seq

        logger.info("Successfully resumed session on shard ID {}, replayed"
                    "{} new events.".format(gw.shard_id, new_events))
        await self.client.fire_event("resumed", new_events, gateway=gw)

    async def handle_user_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when the bot's user is updated.
        """
        id = event_data.get("id")

        self._user.id = int(id)
        self._user.username = event_data.get("username", self._user.username)
        self._user.discriminator = event_data.get("discriminator", self._user.discriminator)
        self._user.avatar_hash = event_data.get("avatar", self._user.avatar_hash)

        await self.client.fire_event("user_update", gateway=gw)

    async def handle_presence_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a member changes game.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        # awful payloads
        user = event_data.get("user")
        if not user:
            return

        # also awful payloads
        try:
            user_id = int(event_data.get("id"))
        except (ValueError, TypeError):
            return

        if not guild:
            # user presence update
            fr = self._friends.get(user_id)

            if not fr:
                # wtf
                return

            # re-create the user object
            if "username" in user:
                # full user object
                self._friends[user_id] = self.make_user(user,
                                                        user_klass=RelationshipUser,
                                                        override_cache=True)
                fr = self._friends[user_id]

            fr.presence.status = event_data.get("status")
            game = event_data.get("game")
            fr.presence.game = game

            await self.client.fire_event("friend_update", fr, gateway=gw)
            return

        # try and create a new member from the presence update
        member = guild.members.get(user_id)
        if member is None:
            # create the member from the presence
            # we only pass the User here as we're about to update everything
            member = Member(client=self.client, user=event_data["user"])
            old_member = None
        else:
            old_member = member._copy()

        # Update the member's presence
        member.presence.status = event_data.get("status")
        member.presence.game = event_data.get("game", {})

        # copy the roles if it exists
        roles = event_data.get("roles", [])
        if roles:
            # clear roles
            member.role_ids = [int(rid) for rid in roles]

        # update the nickname
        member.nickname = event_data.get("nick", member.nickname)

        user = member.user
        if not isinstance(user, RelationshipUser):
            # recreate the user object, so the user is properly cached
            if "username" in event_data["user"]:
                self.make_user(event_data["user"], override_cache=True)

        await self.client.fire_event("member_update", old_member, member, gateway=gw)

    async def handle_presences_replace(self, gw: 'gateway.Gateway', event_data: dict):
        # TODO
        print("P_R", event_data)

    async def handle_guild_members_chunk(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a chunk of members has arrived.
        """
        id = int(event_data.get("guild_id"))
        guild = self._guilds.get(id)

        if not guild:
            logger.warning("Got a chunk for a Guild that doesn't exist...")
            return

        members = event_data.get("members", [])
        logger.info("Got a chunk of {} members in guild {} "
                    "on shard {}".format(len(members), guild.name or guild.id, guild.shard_id))

        guild._handle_member_chunk(event_data.get("members"))
        await self.client.fire_event("guild_chunk", guild, len(members), gateway=gw)

        if guild._chunks_left <= 0:
            # Set the finished chunking event.
            await guild._finished_chunking.set()
            await self.client.fire_event("guild_available", guild, gateway=gw)

        # Check if we have all chunks.
        await self._check_ready(gw, guild)

    async def handle_guild_sync(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a guild is synced.
        """
        id = int(event_data.get("id", 0))
        guild = self._guilds.get(id)

        if not guild:
            # why
            logger.warning("Got sync for guild we're not in...")
            return

        large = event_data.get("large", None)
        if large is not None:
            guild._large = large

        members = event_data.get("members", [])
        # same logic as a guild chunk
        guild._handle_member_chunk(members)

        presences = event_data.get("presences", [])

        for presence in presences:
            u_id = presence["user"]["id"]
            member = guild.members.get(int(u_id))

            if not member:
                continue

            member.presence = Presence(**presence)

        logger.info("Processed a guild sync for guild {} with "
                    "{} members and {} presences.".format(guild.name, len(members), len(presences)))

        await self.client.fire_event("guild_sync", guild, len(members),
                                     len(presences), gateway=gw)

    async def handle_guild_create(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when GUILD_CREATE is dispatched.
        """
        id = int(event_data.get("id", 0))
        guild = self._guilds.get(id)

        had_guild = True
        if guild:
            guild.from_guild_create(**event_data)
        else:
            had_guild = False
            guild = Guild(self.client, **event_data)
            self._guilds[guild.id] = guild

        guild.shard_id = gw.shard_id
        try:
            guild.me.presence.game = gw.game
            guild.me.presence.status = gw.status
        except AttributeError:
            # unavailable guilds etc
            pass

        # Dispatch the event if we're ready (i.e not streaming)
        if self.is_ready(gw.shard_id).is_set():
            if had_guild:
                await self.client.fire_event("guild_available", guild, gateway=gw)
            else:
                # We didn't have it before, so we just joined it.
                # Hence, we fire a `guild_join` event.
                # Parse the guild.
                guild.from_guild_create(**event_data)
                await self.client.fire_event("guild_join", guild, gateway=gw)

                logger.info("Joined guild {} ({}), requesting members if applicable"
                            .format(guild.name, guild.id))
                if guild.large:
                    await gw.request_chunks([guild])
                if self._user.bot:
                    await gw.send_guild_sync([guild])

        else:
            logger.debug("Streamed guild: {} ({})".format(guild.name, guild.id))
            await self.client.fire_event("guild_streamed", guild, gateway=gw)

        if self._user.bot:
            if not guild.unavailable and guild.large:
                # mark this guild as a chunking guild
                self._mark_for_chunking(gw, guild)
            else:
                # set finished_chunking now
                await guild._finished_chunking.set()

        await self._check_ready(gw, guild)

    async def handle_guild_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when GUILD_UPDATE is dispatched.
        """
        id = int(event_data.get("id", 0))
        guild = self._guilds.get(id)

        if not guild:
            return

        old_guild = copy.copy(guild)

        guild.unavailable = event_data.get("unavailable", False)
        guild.name = event_data.get("name", guild.name)
        guild.member_count = event_data.get("member_count", guild.member_count)
        if not guild.member_count:
            guild.member_count = len(guild._members)
        guild._large = event_data.get("large", guild._large)
        guild._icon_hash = event_data.get("icon", guild._icon_hash)
        guild._splash_hash = event_data.get("splash", guild._splash_hash)
        guild.region = event_data.get("region", guild.region)
        guild.features = event_data.get("features", guild.features)

        guild.mfa_level = MFALevel(event_data.get("mfa_level", guild.mfa_level))
        guild.verification_level = VerificationLevel(event_data.get("verification_level",
                                                                    guild.verification_level))
        guild.notification_level = NotificationLevel(
            event_data.get("default_message_notifications", guild.notification_level)
        )
        guild.content_filter_level = ContentFilterLevel(
            event_data.get("explicit_content_filter", guild.content_filter_level)
        )

        guild.system_channel_id = int_or_none(event_data.get("system_channel_id"),
                                              guild.system_channel_id)

        guild.afk_channel_id = int_or_none(event_data.get("afk_channel"), guild.afk_channel_id)
        guild.afk_timeout = event_data.get("afk_timeout", guild.afk_timeout)
        guild.owner_id = int_or_none(event_data.get("owner_id"), guild.owner_id)

        await self.client.fire_event("guild_update", old_guild, guild, gateway=gw)

    async def handle_guild_delete(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a guild becomes unavailable.
        """
        guild_id = int(event_data.get("id", 0))
        # Check if the `unavailable` flag is there.
        # If it is, we want to semi-discard this event, because all it means is the guild
        # becomes unavailable.
        if event_data.get("unavailable", False):
            # Set the guild to unavailable, but don't delete it.
            guild = self._guilds.get(guild_id)
            if guild:
                guild.unavailable = True
                await self.client.fire_event("guild_unavailable", guild, gateway=gw)

        else:
            # We've left this guild - clear it from our dictionary of guilds.
            guild = self._guilds.pop(guild_id, None)
            if guild:
                await self.client.fire_event("guild_leave", guild, gateway=gw)
                for member in guild._members.values():
                    # use member.id to avoid user lookup
                    self._check_decache_user(member.id)

    async def handle_guild_emojis_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a guild updates its emojis.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        old_guild = guild._copy()
        emojis = event_data.get("emojis", [])
        guild._handle_emojis(emojis)

        await self.client.fire_event("guild_emojis_update", old_guild, guild, gateway=gw)

    async def handle_message_create(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when MESSAGE_CREATE is dispatched.
        """
        message = self.make_message(event_data)
        if not message:
            return

        # Hope that messages are ordered!
        message.channel._last_message_id = message.id

        if self._user in message.mentions:
            await self.client.fire_event("message_mentioned", message, gateway=gw)

        await self.client.fire_event("message_create", message, gateway=gw)

    async def handle_message_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when MESSAGE_UPDATE is dispatched.
        """
        new_message = self.make_message(event_data, cache=False)
        if not new_message:
            return

        # Try and find the old message.
        old_message = self._find_message(new_message.id)
        if not old_message:
            return

        self._messages.remove(old_message)
        self._messages.append(new_message)

        if old_message.content != new_message.content:
            # Fire a message_edit, as well as a message_update, because the content differs.
            await self.client.fire_event("message_edit", old_message, new_message, gateway=gw)

        await self.client.fire_event("message_update", old_message, new_message, gateway=gw)

    async def handle_message_delete(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when MESSAGE_DELETE is dispatched.
        """
        message_id = int(event_data.get("id"))
        message = self._find_message(message_id)

        if not message:
            return

        await self.client.fire_event("message_delete", message, gateway=gw)

    async def handle_message_delete_bulk(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when MESSAGE_DELETE_BULK is dispatched.
        """
        messages = []
        for message in event_data.get("ids", []):
            message = self._find_message(int(message))
            if not message:
                continue

            messages.append(message)

        await self.client.fire_event("message_delete_bulk", messages, gateway=gw)

    def _find_emoji(self, emoji_data: dict):
        if emoji_data.get("id", None) is None:
            # str only
            return emoji_data["name"]

        # try and get it from the guilds
        for guild in self.guilds.values():
            em = guild.emojis.get(int(emoji_data["id"]))
            if em:
                return em

    async def handle_message_reaction_add(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a reaction is added to a message.
        """
        message_id = event_data.get("message_id")
        if not message_id:
            return

        message_id = int(message_id)
        message = self._find_message(message_id)

        if not message:
            return

        # complex filter
        def _f(r: Reaction):
            if not r.emoji:
                return False

            e = self._find_emoji(event_data["emoji"])
            if not e:
                # ¯\_(ツ)_/¯
                return False

            return r.emoji == e

        reaction = next(filter(_f, message.reactions), None)

        if not reaction:
            emoji = event_data.get("emoji", {})
            # no useful args are added
            reaction = Reaction()

            if "id" in emoji and emoji["id"] is not None:
                emoji_obb = message.guild.emojis.get(int(emoji["id"]))
                if emoji_obb is None:
                    emoji_obb = Emoji(id=emoji["id"], name=emoji["name"])
            else:
                emoji_obb = emoji.get("name", None)

            reaction.emoji = emoji_obb
            message.reactions.append(reaction)
        else:
            # up the count
            reaction.count += 1
            # if our user id matches, we obviously voted on it
            if int(event_data["user_id"]) == self._user.id:
                reaction.me = True

        member_id = int(event_data.get("user_id", 0))
        channel = self.find_channel(int(event_data.get("channel_id", 0)))
        if channel.guild:
            author = channel.guild.members.get(member_id)
        else:
            author = channel.user

        await self.client.fire_event("message_reaction_add", message, author, reaction, gateway=gw)

    async def handle_message_reaction_remove_all(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when all reactions are removed from a message.
        """
        message = self._find_message(int(event_data.get("message_id", 0)))
        if not message:
            return

        reactions = message.reactions.copy()
        message.reactions = []
        await self.client.fire_event("message_reaction_remove_all", message, reactions, gateway=gw)

    async def handle_message_reaction_remove(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a reaction is removed from a message.
        """
        message_id = event_data.get("message_id")
        if not message_id:
            return

        message_id = int(message_id)
        message = self._find_message(message_id)

        if not message:
            return

        def _f(r: Reaction):
            if not r.emoji:
                return False

            e = self._find_emoji(event_data["emoji"])
            if not e:
                # ¯\_(ツ)_/¯
                return False

        reaction = next(filter(_f, message.reactions), None)
        if not reaction:
            # nothing to do
            return

        reaction.count -= 1
        if int(event_data["user_id"]) == self._user.id:
            reaction.me = False

        if reaction.count == 0:
            message.reactions.remove(reaction)

        await self.client.fire_event("message_reaction_remove", message, reaction, gateway=gw)

    async def handle_guild_member_add(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a guild adds a new member.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member = Member(self.client, **event_data)
        member.guild_id = guild.id

        guild._members[member.id] = member
        guild.member_count += 1
        await self.client.fire_event("member_join", member, gateway=gw)

    async def handle_guild_member_remove(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a guild removes a member.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member = guild._members.pop(int(event_data["user"]["id"]), None)
        guild.member_count -= 1
        if not member:
            # We can't see the member, so don't fire an event for it.
            return

        await self.client.fire_event("member_leave", member, gateway=gw)

    async def handle_guild_member_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a guild member is updated.
        """
        print(event_data)
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member_id = int(event_data["user"]["id"])
        member = guild.members.get(member_id)

        if not member:
            return

        # Make a copy of the member for the old previous reference.
        old_member = member._copy()
        # Re-create the user object.
        # self.make_user(event_data["user"], override_cache=True)
        # self._users[member.user.id] = member.user

        # Overwrite roles, we want to get rid of any roles that are stale.
        if "roles" in event_data:
            member.role_ids = [int(i) for i in event_data.get("roles", [])]

        guild._members[member.id] = member
        member.nickname = event_data.get("nickname", member.nickname)

        await self.client.fire_event("member_update", old_member, member, gateway=gw)

    async def handle_guild_ban_add(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a ban is added to a guild.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if guild is None:
            return

        member_id = int(event_data["user"]["id"])
        member = guild.members.get(member_id)

        if not member:
            # Dispatch to `user_ban` instead of `member_ban`.
            user = self.make_user(event_data["user"])
            await self.client.fire_event("user_ban", guild, user, gateway=gw)
            return

        await self.client.fire_event("member_ban", member, gateway=gw)

    async def handle_guild_ban_remove(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a ban is removed from a guild.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if guild is None:
            return

        user = self.make_user(event_data["user"])
        await self.client.fire_event("user_unban", guild, user, gateway=gw)

    async def handle_channel_create(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a channel is created.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        channel = Channel(self.client, **event_data)
        if channel.private:
            self._private_channels[channel.id] = channel
        else:
            channel.guild_id = guild.id
            channel._update_overwrites((event_data.get("permission_overwrites", [])))
            if channel.id not in guild._channels:
                guild._channels[channel.id] = channel
            else:
                channel = guild._channels[channel.id]

        await self.client.fire_event("channel_create", channel, gateway=gw)

    async def handle_channel_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a channel is updated.
        """
        channel_id = int(event_data.get("id"))
        channel = self.find_channel(channel_id)

        if not channel:
            return

        old_channel = channel._copy()

        channel.name = event_data.get("name", channel.name)
        channel.position = event_data.get("position", channel.position)
        channel.topic = event_data.get("topic", channel.topic)
        channel.nsfw = event_data.get("nsfw", channel.nsfw)
        channel.icon_hash = event_data.get("icon_hash", channel.icon_hash)
        channel.owner_id = int_or_none(event_data.get("owner_id"), channel.owner_id)
        channel.parent_id = int_or_none(event_data.get("parent_id"), channel.parent_id)

        channel._update_overwrites(event_data.get("permission_overwrites", []))
        await self.client.fire_event("channel_update", old_channel, channel, gateway=gw)

    async def handle_channel_delete(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a channel is deleted.
        """
        channel_id = int(event_data.get("channel_id", 0))
        channel = self.find_channel(channel_id)

        if not channel:
            return

        if channel.private:
            del self._private_channels[channel.id]
        else:
            del channel.guild._channels[channel.id]

        await self.client.fire_event("channel_delete", channel, gateway=gw)

    async def handle_guild_role_create(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a role is created.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        role_data = event_data.get("role")  # type: dict
        if role_data is None:
            return

        role_id = int(role_data.get("id", 0))
        if not role_id:
            return

        if role_id not in guild._roles:
            role = Role(self.client, **role_data)
            role.guild_id = guild.id
            guild._roles[role_id] = role
        else:
            # thinking
            role = guild._roles[role_id]

        await self.client.fire_event("role_create", role, gateway=gw)

    async def handle_guild_role_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a role is updated.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        role_data = event_data.get("role")  # type: dict
        if role_data is None:
            return

        role_id = int(role_data.get("id", 0))
        if not role_id:
            return

        role = guild.roles.get(role_id)
        if not role:
            return

        old_role = role._copy()

        # Update all the fields on the role.
        event_data = event_data.get("role", {})
        role.colour = event_data.get("color", 0)
        role.name = event_data.get("name")
        role.position = event_data.get("position")
        role.hoisted = event_data.get("hoisted")
        role.mentionable = event_data.get("mentionable")
        role.managed = event_data.get("managed")
        role.permissions = Permissions(event_data.get("permissions", 0))

        await self.client.fire_event("role_update", old_role, role, gateway=gw)

    async def handle_guild_role_delete(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a role is deleted.
        """
        guild_id = int(event_data.get("guild_id", 0))
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        role = guild._roles.pop(int(event_data["role_id"]), None)
        if not role:
            return

        # Remove the role from all members.
        for member in guild.members.values():
            try:
                member.role_ids.remove(role.id)
            except ValueError:
                continue

        await self.client.fire_event("role_delete", role, gateway=gw)

    async def handle_typing_start(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a user starts typing.
        """
        user_id = int(event_data.get("user_id"))
        channel_id = int(event_data.get("channel_id"))

        channel = self.find_channel(channel_id)
        if not channel:
            return

        if not channel.private:
            member = channel.guild.members.get(user_id)
            if not member:
                return
            await self.client.fire_event("member_typing", channel, member, gateway=gw)
        else:
            user = channel.recipients.get(user_id)
            if user is None:
                return

            await self.client.fire_event("user_typing", channel, user, gateway=gw)

    # Voice bullshit
    async def handle_voice_server_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a voice server update packet is dispatched.
        """
        # This is an internal event, so we do NOT dispatch it.
        # Instead, store some state internally.
        guild_id = event_data.get("guild_id")
        if not guild_id:
            # thanks
            return

        events, state = self.__voice_state_crap[int(guild_id)]

        state.update({
            "token": event_data.get("token"),
            "endpoint": event_data.get("endpoint"),
        })

        # Set the VOICE_SERVER_UPDATE event.
        await events[0].set()

    async def handle_voice_state_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a member's voice state changes.
        """
        guild_id = int(event_data.get("guild_id", 0))

        # If user_id == self._user.id, it's voice conn bullshit
        user_id = int(event_data.get("user_id", 0))
        if user_id == self._user.id:
            # YAY
            events, state = self.__voice_state_crap[guild_id]
            state.update({
                "session_id": event_data.get("session_id")
            })
            # 2nd one is voice_state_update event
            await events[1].set()
            return

        # get the guild and member
        guild = self._guilds.get(guild_id)

        if not guild:
            return

        member = guild.members.get(user_id)
        if not member:
            return

        channel_id = event_data.get("channel_id", 0)
        if channel_id is None:
            # disconnect!
            new_voice_state = None
        else:
            new_voice_state = VoiceState(**event_data)
            new_voice_state.guild_id = guild.id

        # copy the voice states
        old_voice_state = guild._voice_states.pop(user_id)
        if new_voice_state is not None:
            guild._voice_states[new_voice_state.user_id] = new_voice_state

        await self.client.fire_event("voice_state_update", member, old_voice_state,
                                     new_voice_state, gateway=gw)

    async def handle_webhooks_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a channel has a webhook updated.

        This event is effectively useless.
        """

    # TODO: Flesh these out
    async def handle_channel_pins_update(self, gw: 'gateway.Gateway', event_data: dict):
        pass

    async def handle_channel_pins_ack(self, gw: 'gateway.Gateway', event_data: dict):
        pass

    # Userbot only events.
    async def handle_user_settings_update(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when the current user's settings update.
        """
        old_settings = self._user.settings.copy()

        dict.update(self._user.settings, **event_data)
        # make sure to update the guild order
        guild_order = event_data.get("guild_positions")
        if guild_order:
            self._guilds.order = [int(x) for x in guild_order]

        # update status, if applicable
        new_status = Status(self._user.settings.get("status", old_settings.get("status", "ONLINE")))
        for guild in self.guilds.values():
            if new_status.strength > guild.me.status.strength:
                guild.me.status = new_status

        await self.client.fire_event("user_settings_update", old_settings, self._user.settings,
                                     gateway=gw)

    async def handle_message_ack(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a message is acknowledged.
        """
        channel = self.find_channel(int(event_data.get("channel_id", 0)))
        try:
            message = self._find_message(int(event_data.get("message_id", 0)))
        except (ValueError, TypeError):
            # message_id is None, wtf?
            return

        if channel is None:
            return

        if message is None:
            return

        await self.client.fire_event("message_ack", channel, message, gateway=gw)

    async def handle_relationship_add(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a relationship is added.
        """
        type_ = event_data.get("type", 0)

        if type_ == 1:
            # FR accepted
            u = RelationshipUser(client=self.client, **event_data.get("user"))
            u.type_ = FriendType.FRIEND
            self._friends[u.id] = u
        elif type_ == 2:
            u = RelationshipUser(client=self.client, **event_data.get("user"))
            u.type_ = FriendType.BLOCKED
            self._blocked[u.id] = u
        else:
            return

        self._users[u.id] = u

        await self.client.fire_event("relationship_add", u, gateway=gw)

    async def handle_relationship_remove(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a relationship is removed.
        """
        type_ = event_data.get("type", 0)
        u_id = int(event_data.get("id", 0))

        if type_ == 1:
            u = self._friends.pop(u_id, None)
        elif type_ == 2:
            u = self._blocked.pop(u_id, None)
        else:
            return

        # replace the type in `_users` with a generic user
        # this wont cause race conditions due to the GIL etc
        del self._users[u_id]
        new_user = self.make_user(
            {
                "id": u_id,
                "username": u.username,
                "discriminator": u.discriminator,
                "avatar": u.avatar_hash,
                "bot": u.bot
            }
        )
        self._users[u_id] = new_user

        # maybe decache it anyway
        self._check_decache_user(u_id)

        await self.client.fire_event("relationship_remove", u, gateway=gw)

    async def handle_channel_recipient_add(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a recipient is added to a channel.
        """
        user = event_data.get("user", {})
        id = int(event_data.get("channel_id", 0))

        user = self._users.get(int(user.get("id", 0)))

        channel = self.find_channel(channel_id=id)
        if channel is None:
            return

        channel._recipients[user.id] = user

        await self.client.fire_event("group_user_add", channel, user, gateway=gw)

    async def handle_channel_recipient_remove(self, gw: 'gateway.Gateway', event_data: dict):
        """
        Called when a recipient is removed a channel.
        """
        user = event_data.get("user", {})
        id = int(event_data.get("channel_id", 0))

        user = self._users.get(int(user.get("id", 0)))
        channel = self.find_channel(channel_id=id)
        if channel is None:
            return

        if user in channel.recipients.values():
            channel._recipients.pop(user.id, None)
            await self.client.fire_event("group_user_remove", channel, user, gateway=gw)
