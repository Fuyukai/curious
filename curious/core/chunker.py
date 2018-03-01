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

import logging
from collections import defaultdict
from typing import List, MutableMapping

from curious.core import client as md_client
from curious.core.event import EventContext, event
from curious.dataclasses import guild as md_guild

logger = logging.getLogger(__name__)


class Chunker(object):
    """
    Handles chunking for guilds.
    """
    def __init__(self, client, batch_size: int = 75):
        #: The client associated with this chunker.
        self.client: md_client.Client = client

        #: The number of guilds to send in a single shard request.
        self.batch_size = max(batch_size, 45)  # 2500/60 is 41 so we'll never go above the wsrl

        #: A mapping of shard_id -> List[Guild] of guilds we need to send chunking for.
        self._pending: MutableMapping[int, List[md_guild.Guild]] = defaultdict(list)

        #: A mapping of shard_id -> bool for if we're connected or not.
        self._connected: MutableMapping[int, bool] = defaultdict(lambda: False)

        #: A mapping of shard_id -> bool for if we've fired a READY before.
        self._ready: MutableMapping[int, bool] = defaultdict(lambda: False)

    def register_events(self, event_handler):
        """
        Registers the events for this chunk handler.
        """
        event_handler.add_event(self.potentially_add_to_pending)
        event_handler.add_event(self.handle_new_guild)
        event_handler.add_event(self.handle_member_chunk)
        event_handler.add_event(self.unconditionally_chunk_rest)

    async def fire_chunks(self, shard_id: int, guilds: 'List[md_guild.Guild]'):
        """
        Fires off GUILD_MEMBER_CHUNK requests for the list of guilds.
        """
        logger.info("Firing a chunk request for %s guilds", len(guilds))
        ids = [guild.id for guild in guilds]
        gateway = self.client._gateways[shard_id]
        await gateway.send_guild_chunks(ids)

    async def potentially_fire_chunks(self, shard_id: int = None):
        """
        Potentially fires chunks for guilds if we need to.

        This will only fire if the shard specified has more than ``batch_size`` guilds pending
        chunking.

        :param shard_id: The shard ID to fire, or None if all shards need to be checked.
        """
        if shard_id is None:
            shard_ids = self._pending.keys()
        else:
            shard_ids = [shard_id]

        for shard in shard_ids:
            guilds = self._pending[shard]
            if not guilds:
                # wtf
                continue

            if len(guilds) < self.batch_size:
                # if all are available, skip the exit check
                if any(guild.unavailable for guild in self.client.guilds_for(shard)):
                    continue

            # pray for the gil
            self._pending[shard] = []
            await self.fire_chunks(shard, guilds)

    async def _potentially_fire_ready(self, shard_id: int):
        """
        Potentially fires READY.
        """
        # don't fire a ready if we haven't even got a connected event
        if not self._connected[shard_id]:
            return

        # don't fire one if we've already fired one
        if self._ready[shard_id]:
            return

        guilds = self.client.guilds_for(shard_id)

        # if they're unavailable we clearly don't have the members
        if any(guild.unavailable is True for guild in guilds):
            return

        # if they're not all set then we don't want to fire ready at all
        if not all(guild._finished_chunking.is_set() for guild in guilds if guild.large):
            return

        # fire a ready
        gateway = self.client._gateways[shard_id]
        await self.client.events.fire_event("ready", gateway=gateway, client=self.client)
        self._ready[shard_id] = True

    @event("guild_chunk")
    async def handle_member_chunk(self, ctx: EventContext, guild: 'md_guild.Guild', members: int):
        """
        Checks if we can fire ready or not.
        """
        # the state handles the finer details of the event, thankfully
        await self._potentially_fire_ready(ctx.shard_id)

    @event("guild_streamed")
    async def potentially_add_to_pending(self, ctx: EventContext, guild: 'md_guild.Guild'):
        """
        Potentially adds a guild to the pending count.
        """
        if guild.large:
            logger.debug("Added guild `%s` to chunk pending", guild.id)
            self._pending[ctx.shard_id].append(guild)

        await self.potentially_fire_chunks(shard_id=ctx.shard_id)

    @event("guild_available")
    @event("guild_joined")
    async def handle_new_guild(self, ctx: EventContext, guild: 'md_guild.Guild'):
        """
        Handles a new guild (just become available for) has just joined.
        """
        # immediately chunk
        await self.fire_chunks(ctx.shard_id, [guild])

    # clear any pending guilds
    @event("connect")
    async def unconditionally_chunk_rest(self, ctx: EventContext):
        """
        Unconditionally chunks the current guilds that are pending.
        """
        # clear ready
        self._ready[ctx.shard_id] = False

        guilds = self._pending[ctx.shard_id]
        if guilds:
            await self.fire_chunks(ctx.shard_id, guilds)

        self._connected[ctx.shard_id] = True
        await self._potentially_fire_ready(ctx.shard_id)

