"""
Websocket gateway code.

.. currentmodule:: curious.core.gateway
"""
import collections
import enum
import logging
import queue
import sys
import threading
import time
import typing
import warnings
import zlib

try:
    # Prefer ETF data.
    import earl


    def _loader(data: bytes):
        return earl.unpack(data, encoding="utf-8", encode_binary_ext=True)


    def _dumper(data: dict):
        return earl.pack(data)


    _fmt = "etf"
except ImportError:
    try:
        import ujson as json
    except ImportError:
        import json


    def _loader(data: str):
        return json.loads(data)


    def _dumper(data: dict):
        return json.dumps(data)


    _fmt = "json"
    warnings.warn("Using JSON parser for gateway - install `Earl-ETF` to use ETF!")

import curio
from curio.thread import AWAIT, async_thread
from cuiows.exc import WebsocketClosedError
from cuiows import WSClient

from curious.dataclasses.presence import Game, Status


# Signalling exceptions.
class ReconnectWebsocket(Exception):
    """
    Signals that the websocket needs to reconnect.
    """


class ChunkGuilds(Exception):
    """
    Signals that we need to begin downloading all guild member chunks.
    """


class GatewayOp(enum.IntEnum):
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE = 3
    VOICE_STATE = 4
    VOICE_PING = 5
    RESUME = 6
    RECONNECT = 7
    REQUEST_MEMBERS = 8
    INVALIDATE_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    GUILD_SYNC = 12


class HeartbeatStats:
    def __init__(self):
        self.heartbeats = 0
        self.heartbeat_acks = 0

        self.last_heartbeat = None
        self.last_ack = None

    @property
    def gw_time(self) -> float:
        """
        :return: The time the most recent heartbeat and heartbeat_ack.
        """
        return self.last_ack - self.last_heartbeat


@async_thread(daemon=True)
def _heartbeat_loop(gw: 'Gateway', heartbeat_interval: float):
    """
    Heartbeat looper that loops and sends heartbeats to the gateway.

    :param gw: The gateway to handle.
    """
    # async threads!
    gw.logger.debug("Sending initial heartbeat.")
    AWAIT(gw.send_heartbeat())
    while True:
        # this is similar to the normal threaded event waiter
        # it will time out after heartbeat_interval seconds.
        try:
            AWAIT(curio.timeout_after(heartbeat_interval, gw._stop_heartbeating.wait()))
        except curio.TaskTimeout:
            pass
        else:
            break

        try:
            AWAIT(gw.send_heartbeat())
        except ReconnectWebsocket:
            break


class Gateway(object):
    """
    Interacts with the Discord Gateway.
    """
    #: The current gateway version to connect to Discord via.
    GATEWAY_VERSION = 6

    def __init__(self, token: str, connection_state, *,
                 large_threshold: int = 250):
        """
        :param token: The bot token to connect with.
        """
        #: The token used to identify with.
        self.token = token

        #: The current websocket connection.
        self.websocket = None  # type: WSClient

        #: The current sequence number.
        self.sequence_num = 0

        #: The connection state used for this connection.
        self.state = connection_state

        #: The shard ID this gateway is representing.
        self.shard_id = 0
        #: The number of shards the client is connected to.
        self.shard_count = 1

        #: The current session ID for this gateway.
        self.session_id = None

        #: The current heartbeat statistic counter for this gateway.
        self.hb_stats = HeartbeatStats()

        #: The current game for this gateway.
        #: Only set when sending a change status packet.
        self.game = None
        #: The current status for this gateway.
        self.status = None

        #: The "large threshold" for this Gateway.
        #: For guilds with members above this number, offline members will not be sent.
        self.large_threshold = min(250, large_threshold)  # bound to 250

        #: The data format for this gateway.
        self.format = _fmt

        self._prev_seq = 0
        self._dispatches_handled = collections.Counter()
        self._enqueued_guilds = []
        self._stop_heartbeating = curio.Event()
        self._logger = None
        self._cached_gateway_url = None  # type: str
        self._open = False

    @property
    def logger(self):
        if self._logger:
            return self._logger

        self._logger = logging.getLogger("curious.gateway:shard-{}".format(self.shard_id))
        return self._logger

    async def connect(self, url: str):
        """
        Connects the client to the websocket.

        This does not do ANY handshake steps.
        :param url: The URL to connect to.
        """
        self.logger.info("Opening connection to {}".format(url))
        try:
            self.websocket = await curio.timeout_after(5, WSClient.connect(url))
        except curio.TaskTimeout as e:
            raise ReconnectWebsocket from e
        self.logger.info("Connected to gateway!")
        self._open = True
        return self.websocket

    async def _start_heartbeating(self, heartbeat_interval: float) -> threading.Thread:
        """
        Starts the heartbeat thread.
        :param heartbeat_interval: The number of seconds between each heartbeat.
        """
        if not self._stop_heartbeating.is_set():
            # cancel some poor thread elsewhere
            await self._stop_heartbeating.set()
            del self._stop_heartbeating

        self._stop_heartbeating = curio.Event()

        # dont reference the task - it'll die by itself
        task = await curio.spawn(_heartbeat_loop(self, heartbeat_interval), daemon=True)

        return task

    # Utility methods.
    async def _close(self):
        """
        Closes the connection.
        """
        self._open = False
        await self._stop_heartbeating.set()

    async def _send(self, data):
        """
        Sends some data.

        This will actually send the data down the websocket, unlike `send` which only pretends to.
        """
        # Check if heartbeats have drifted.
        if self.hb_stats.heartbeat_acks + 2 < self.hb_stats.heartbeats:
            self.logger.error("Heartbeats have drifted, closing connection!")
            await self.websocket.close_now(reason="Heartbeats timed out!")
            await self._close()
            raise ReconnectWebsocket

        try:
            await self.websocket.send(data)
        except WebsocketClosedError:
            await self._close()

    def _send_dict(self, payload: dict):
        """
        Sends a dict to be packed down the gateway.

        This is a private method - use :meth:`send` instead.

        :param payload: The payload to send.
        """
        data = _dumper(payload)
        return self._send(data)

    async def send(self, data: typing.Any):
        """
        Sends a variable type of data down the gateway.
        """
        try:
            if isinstance(data, dict):
                await self._send_dict(data)
            else:
                await self._send(data)
        except queue.Full as e:
            raise RuntimeError("Gateway queue is full - this should never happen!") from e

    # Sending events.
    async def send_identify(self):
        """
        Sends an IDENTIFY packet.
        """
        payload = {
            "op": GatewayOp.IDENTIFY,
            "d": {
                "token": self.token,
                "properties": {
                    "$os": sys.platform,
                    "$browser": "curious",
                    "$device": "curious",
                    "$referrer": "",
                    "$referring_domain": ""
                },
                "compress": True,
                "large_threshold": self.large_threshold,
                "v": self.GATEWAY_VERSION,
                "shard": [self.shard_id, self.shard_count]
            }
        }

        await self._send_dict(payload)

    async def send_resume(self):
        """
        Sends a RESUME packet.
        """
        payload = {
            "op": GatewayOp.RESUME,
            "d": {
                "token": self.token,
                "session_id": self.session_id,
                "seq": self.sequence_num
            }
        }

        await self._send_dict(payload)

    async def send_status(self, game: Game, status: Status, *,
                          afk: bool=False):
        """
        Sends a PRESENCE_UPDATE packet.

        :param game: The game object to send.
        :param status: The status object to send.
        :param afk: Is this gateway AFK?
            This should be True for self bots.
        """
        payload = {
            "op": GatewayOp.PRESENCE,
            "d": {
                "game": game.to_dict() if game else None,
                "status": status.value,
                "afk": afk,
                "since": None if not afk else int(time.time() * 1000)
            }
        }

        self.game = game
        self.status = status

        # Update our game() object on all guilds on this shard.
        for guild in self.state.guilds_for_shard(self.shard_id):
            try:
                guild.me.presence.game = game
                guild.me.presence.status = status
            except AttributeError:
                # sent before our member object exists - i.e just after READY happens
                # we can ignore this
                pass

        await self._send_dict(payload)

    async def send_voice_state_update(self, guild_id: int, channel_id: int):
        """
        Sends a voice state update packet.

        :param guild_id: The guild ID to update in.
        :param channel_id: The channel ID to update in.
        """

        payload = {
            "op": GatewayOp.VOICE_STATE,
            "d": {
                "guild_id": str(guild_id),
                "channel_id": str(channel_id),
                "self_mute": False,
                "self_deaf": False,
            }
        }

        await self._send_dict(payload)

    async def send_heartbeat(self):
        """
        Sends a single heartbeat.
        """
        hb = self._get_heartbeat()
        self.logger.debug("Heartbeating with sequence {}".format(hb["d"]))

        # increment the stats
        self.hb_stats.heartbeats += 1
        self.hb_stats.last_heartbeat = time.monotonic()

        await self.state.client.fire_event("gateway_heartbeated", self.hb_stats, gateway=self)

        await self._send_dict(hb)
        return self.hb_stats.heartbeats

    async def send_guild_sync(self, guilds):
        """
        Sends a guild sync packet.

        :param guilds: A list of guild IDs to request syncing for.
        """
        payload = {
            "op": GatewayOp.GUILD_SYNC,
            "d": [str(g.id) for g in guilds]
        }

        await self._send_dict(payload)

    async def request_chunks(self, guilds):
        """
        Requests member chunks from a guild.

        :param guilds: A list of guild IDs to request chunks for.
        """
        payload = {
            "op": GatewayOp.REQUEST_MEMBERS,
            "d": {
                "guild_id": [str(guild.id) for guild in guilds],
                "query": "",
                "limit": 0  # Request ALL!
            }
        }

        await self._send_dict(payload)

    @classmethod
    async def from_token(cls, token: str, state, gateway_url: str,
                         *, shard_id: int = 0, shard_count: int = 1,
                         **kwargs) -> 'Gateway':
        """
        Creates a new gateway connection from a token.

        :param token: The token to pass in.
            This must be a bot user token - user tokens are not supported.
        :param state: The connection state that is attached to this client.
        :param gateway_url: The gateway URL to connect.
        :param shard_id: The shard ID of this bot.
        :param shard_count: The number of shards to start the bot with.

        :return: A new :class:`Gateway` that is connected to the API.
        """
        obb = cls(token, state, **kwargs)
        obb.shard_id = shard_id
        obb.shard_count = shard_count

        gateway_url += "?v={}&encoding={}".format(cls.GATEWAY_VERSION, _fmt)
        obb._cached_gateway_url = gateway_url

        await obb.connect(gateway_url)

        # send IDENTIFY
        obb.logger.info("Sending IDENTIFY...")
        await obb.send_identify()

        return obb

    async def reconnect(self, *, resume: bool = False):
        """
        Reconnects the bot to the gateway.

        :param resume: Should a RESUME be attempted?
        """
        self.logger.info("Reconnecting to the gateway")

        # reset our heartbeat count
        self.hb_stats.heartbeats = 0
        self.hb_stats.heartbeat_acks = 0

        if not self.websocket.closed:
            await self.websocket.close_now(code=1001, reason="Forcing a reconnect")

        self._open = False

        await self.connect(self._cached_gateway_url)

        if resume:
            # Send the RESUME packet, instead of the IDENTIFY packet.
            self.logger.info("Sending RESUME...")
            await self.send_resume()
        else:
            self.logger.info("Sending IDENTIFY...")
            self.sequence_num = 0
            await self.send_identify()

        return self

    async def _get_chunks(self):
        """
        Called to start chunking all guild members.
        """
        for guild in self._enqueued_guilds:
            guild.start_chunking()
            self.logger.info("Requesting {} member chunk(s) from guild {}."
                             .format(guild._chunks_left, guild.name))

        await self.request_chunks(self._enqueued_guilds)
        self._enqueued_guilds.clear()

    def _get_heartbeat(self):
        return {
            "op": GatewayOp.HEARTBEAT,
            "d": self.sequence_num
        }

    async def next_event(self):
        """
        Gets the next event, in decoded form.
        """
        if not self._open:
            raise WebsocketClosedError(1006, reason="Connection lost")

        try:
            event = await self.websocket.poll()
        except WebsocketClosedError:
            # Close ourselves.
            await self._close()
            raise

        await self.state.client.fire_event("gateway_message_received", event, gateway=self)

        if isinstance(event, (bytes, bytearray)) and _fmt == "json":
            # decompress the message
            event = zlib.decompress(event, 15, 10490000)
            event = event.decode("utf-8")

        if event is None:
            return

        event_data = _loader(event)
        # self.logger.debug("Got event {}".format(event_data))
        await self.state.client.fire_event("gateway_event_received", event_data, gateway=self)

        op = event_data.get('op')
        data = event_data.get('d')
        seq = event_data.get('s')

        if seq is not None:
            # next sequence
            self.sequence_num = seq

        # Switch based on op.
        if op == GatewayOp.HELLO:
            # Start heartbeating, with the specified heartbeat duration.
            await self.state.client.fire_event("gateway_hello", data['_trace'], gateway=self)
            heartbeat_interval = data.get("heartbeat_interval", 45000) / 1000.0
            self.logger.debug("Heartbeating every {} seconds.".format(heartbeat_interval))
            await self._start_heartbeating(heartbeat_interval)
            self.logger.info("Connected to Discord servers {}".format(",".join(data["_trace"])))

        elif op == GatewayOp.HEARTBEAT_ACK:
            await self.state.client.fire_event("gateway_heartbeat_ack", gateway=self)
            self.hb_stats.heartbeat_acks += 1
            self.hb_stats.last_ack = time.monotonic()

        elif op == GatewayOp.HEARTBEAT:
            # Send a heartbeat back.
            await self.state.client.fire_event("gateway_heartbeat_received", gateway=self)
            await self.send_heartbeat()

        elif op == GatewayOp.INVALIDATE_SESSION:
            # Clean up our session.
            should_resume = data
            await self.state.client.fire_event("gateway_invalidate_session", should_resume,
                                               gateway=self)
            if should_resume is True:
                self.logger.debug("Sending RESUME again")
                await self.send_resume()
            else:
                self.logger.warning("Received INVALIDATE_SESSION with d False, re-identifying.")
                self.sequence_num = 0
                self.state._reset(self.shard_id)
                await self.send_identify()

        elif op == GatewayOp.RECONNECT:
            # Try and reconnect to the gateway.
            await self.state.client.fire_event("gateway_reconnect_received", gateway=self)
            self._close()
            raise ReconnectWebsocket()

        elif op == GatewayOp.DISPATCH:
            # Handle the dispatch.
            event = event_data.get("t")
            handler = getattr(self.state, "handle_{}".format(event.lower()), None)

            if handler:
                self.logger.debug("Parsing event {}.".format(event))
                self._dispatches_handled[event] += 1
                await self.state.client.fire_event("gateway_dispatch_received", data, gateway=self)
                # Invoke the handler, which will parse the data and update the cache internally.
                # Yes, handlers are async.
                # This is because curio requires `spawn()` to be async.
                try:
                    await handler(self, data)
                except ChunkGuilds as e:
                    # We need to download all member chunks from this guild.
                    await self._get_chunks()
                except Exception:
                    self.logger.exception("Error decoding event {} with data "
                                          "{}".format(event, data))
                    await self._close()
                    await self.websocket.close_now()
                    raise
            else:
                self.logger.warning("Unhandled event: {}".format(event))

        else:
            try:
                self.logger.warning("Unhandled opcode: {} ({})".format(op, GatewayOp(op)))
            except ValueError:
                self.logger.warning("Unknown opcode: {}".format(op))
