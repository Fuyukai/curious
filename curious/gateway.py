"""
Websocket gateway code.
"""
import enum
import threading
import typing
import queue
import sys
import logging
import zlib

# alternative JSON implementations for speed
try:
    import ujson as json
except ImportError:
    import json

import curio
from curio.task import Task
from cuiows.exc import WebsocketClosedError
from cuiows import WSClient

from curious.dataclasses.status import Game, Status
from curious.state import State


# Signalling exceptions.
class ReconnectWebsocket(Exception):
    """
    Signals that the websocket needs to reconnect.
    """


class ChunkGuild(Exception):
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


class _HeartbeatThread(threading.Thread):
    """
    A subclass of threading.Thread that sends heartbeats every <x> seconds.
    """

    def __init__(self, gw: 'Gateway', heartbeat_interval: float, *args, **kwargs):
        # super() isn't used anywhere else so I'm scared to use it here
        threading.Thread.__init__(self, *args, **kwargs)
        self._gateway = gw
        self._hb_interval = heartbeat_interval

        # The event that tells us to stop heartbeating.
        self._stop_heartbeating = threading.Event()

        # This thread doesn't need to die before Python closes, so we can daemonize.
        # This means that Python won't wait on us to shutdown.
        self.daemon = True

    def run(self):
        """
        Heartbeats every <x> seconds.
        """
        # This uses `Event.wait()` to wait for the next heartbeat.
        # This is effectively a bootleg sleep(), but we can signal it at any time to stop.
        # Which is really cool!

        # Send the first heartbeat.
        self._send_heartbeat()
        while not self._stop_heartbeating.wait(self._hb_interval):
            self._send_heartbeat()

    def get_heartbeat(self):
        """
        :return: A heartbeat packet.
        """
        return {
            "op": int(GatewayOp.HEARTBEAT),
            "d": self._gateway.sequence_num
        }

    def _send_heartbeat(self):
        hb = self.get_heartbeat()

        # Enqueue onto the sending queue.
        self._gateway.logger.debug("Heartbeating with sequence {}".format(hb["d"]))
        self._gateway.send(hb)

        self._gateway.heartbeats += 1


class Gateway(object):
    """
    Interacts with the Discord Gateway.
    """

    GATEWAY_VERSION = 6

    def __init__(self, token: str, connection_state: State):
        """
        :param token: The bot token to connect with.
        """
        #: The token used to identify with.
        self.token = token

        #: The current websocket connection.
        self.websocket = None  # type: WSClient

        #: If the gateway is open or not.
        self._open = False

        #: The current sequence number.
        self.sequence_num = 0

        #: The current logger.
        self._logger = None

        #: The event send queue.
        #: A threadsafe queue is used here so that the keep-alive worker threads can submit a new heartbeat to it and
        #: send the heartbeat through the websocket safely.
        #: All events end up here, and are taken care of in the background.
        self._event_queue = queue.Queue()

        #: The queue reader task.
        #: This reads messages off of the queue and sends them to the gateway.
        self._event_reader = None  # type: Task

        #: The heartbeat thread instance.
        self._heartbeat_thread = None  # type: _HeartbeatThread

        #: The connection state used for this connection.
        self.state = connection_state

        #: The cached gateway URL.
        self._cached_gateway_url = None  # type: str

        #: The shard ID this gateway is representing.
        self.shard_id = 0

        #: The number of shards the client is connected to.
        self.shard_count = 1

        #: The session ID of this connection.
        self.session_id = None

        # Heartbeats and ACKs are tracked by this class to make sure if we send a heartbeat, but the previous one has
        #  not been ACK'd yet, we need to reconnect, as we've lost connection.
        # TODO: Implement this.
        #: The number of heartbeats this connection has sent.
        self.heartbeats = 0

        #: The number of heartbeat ACKs this connection has sent.
        self.heartbeat_acks = 0

        #: The current game for this gateway.
        #: Only set when sending a change status packet.
        self.game = None

        #: The current status for this gateway.
        self.status = None

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
        self.websocket = await WSClient.connect(url)
        self.logger.info("Connected to gateway!")
        self._open = True
        return self.websocket

    def _start_heartbeating(self, heartbeat_interval: float) -> threading.Thread:
        """
        Starts the heartbeat thread.
        :param heartbeat_interval: The number of seconds between each heartbeat.
        """
        if self._heartbeat_thread:
            self._heartbeat_thread._stop_heartbeating.set()

        t = _HeartbeatThread(self, heartbeat_interval)
        t.start()
        self._heartbeat_thread = t
        return t

    # Queue manager.
    async def _send_events(self):
        while self._open:
            # this is cool!
            try:
                next_item = await curio.abide(self._event_queue.get)
            except curio.CancelledError:
                self._event_queue.put_nowait(next_item)
                return
            if isinstance(next_item, dict):
                # this'll come back around in a sec
                self._send_json(next_item)
            else:
                self.logger.debug("Sending websocket data {}".format(next_item))
                await self._send(next_item)

    # Utility methods.
    async def _close(self):
        """
        Closes the connection.
        """
        await self._event_reader.cancel()
        self._open = False

        self._heartbeat_thread._stop_heartbeating.set()

    async def _send(self, data):
        """
        Sends some data.

        This will actually send the data down the websocket, unlike `send` which only pretends to.
        """
        # Check if heartbeats have drifted.
        if self.heartbeat_acks + 2 < self.heartbeats:
            self.logger.error("Heartbeats have drifted, closing connection!")
            await self.websocket.close_now(reason="Heartbeats timed out!")
            await self._close()
            raise ReconnectWebsocket

        try:
            await self.websocket.send(data)
        except WebsocketClosedError:
            await self._close()

    def _send_json(self, payload: dict):
        """
        Sends a JSON payload down the websocket.

        This is a private method - use :meth:`send` instead.

        :param payload: The payload to send.
        """
        data = json.dumps(payload)
        return self.send(data)

    def send(self, data: typing.Any):
        """
        Enqueues some data to be sent down the websocket.

        This does not send the data immediately - it is enqueued to be sent.
        """
        try:
            self._event_queue.put(data, block=False)
        except queue.Full as e:
            raise RuntimeError("Gateway queue is full - this should never happen!") from e

    # Sending events.
    def send_identify(self):
        """
        Sends an IDENTIFY packet.
        """
        payload = {
            "op": GatewayOp.IDENTIFY,
            "d": {
                "token": self.token,
                "properties": {
                    "$os": sys.platform,
                    "$browser": 'curious',
                    "$device": 'curious',
                    "$referrer": "",
                    "$referring_domain": ""
                },
                "compress": True,
                "large_threshold": 250,
                "v": 6,
                "shard": [self.shard_id, self.shard_count]
            }
        }

        self._send_json(payload)

    def send_resume(self):
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

        self._send_json(payload)

    def send_status(self, game: Game, status: Status):
        payload = {
            "op": GatewayOp.PRESENCE,
            "d": {
                "game": game.to_dict() if game else None,
                "status": status.value,
                "afk": False,
                "since": None
            }
        }

        self.game = game
        self.status = status

        # Update our game() object on all guilds on this shard.
        for guild in self.state.guilds_for_shard(self.shard_id):
            guild.me.game = game
            guild.me.status = status

        self._send_json(payload)

    def send_voice_state_update(self, guild_id: int, channel_id: int):
        payload = {
            "op": GatewayOp.VOICE_STATE,
            "d": {
                "guild_id": str(guild_id),
                "channel_id": str(channel_id),
                "self_mute": False,
                "self_deaf": False,
            }
        }

        self._send_json(payload)

    def _request_chunk(self, guild):
        payload = {
            "op": GatewayOp.REQUEST_MEMBERS,
            "d": {
                "guild_id": str(guild.id),
                "query": "",
                "limit": 0  # Request ALL!
            }
        }

        self._send_json(payload)

    @classmethod
    async def from_token(cls, token: str, state: State, gateway_url: str,
                         *, shard_id: int=0, shard_count: int=1) -> 'Gateway':
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
        obb = cls(token, state)
        obb.shard_id = shard_id
        obb.shard_count = shard_count

        gateway_url += "?v={}&encoding=json".format(cls.GATEWAY_VERSION)
        obb._cached_gateway_url = gateway_url

        await obb.connect(gateway_url)

        # Create the event sender task.
        obb._event_reader = await curio.spawn(obb._send_events())

        # send IDENTIFY
        obb.logger.info("Sending IDENTIFY...")
        obb.send_identify()

        return obb

    async def reconnect(self, *, resume: bool = False):
        """
        Reconnects the bot to the gateway.

        :param resume: Should a RESUME be attempted?
        """
        self.logger.info("Reconnecting to the gateway")

        # reset our heartbeat count
        self.heartbeats = 0
        self.heartbeat_acks = 0

        if not self.websocket.closed:
            await self.websocket.close_now(code=1001, reason="Forcing a reconnect")

        self._open = False

        await self.connect(self._cached_gateway_url)
        self._event_reader = await curio.spawn(self._send_events())

        if resume:
            # Send the RESUME packet, instead of the IDENTIFY packet.
            self.logger.info("Sending RESUME...")
            self.send_resume()
        else:
            self.logger.info("Sending IDENTIFY...")
            self.sequence_num = 0
            self.send_identify()

        return self

    def _get_chunks(self, guild):
        """
        Called to start chunking all guild members.
        """
        guild.start_chunking()
        self.logger.info("Requesting {} member chunk(s) from guild {}.".format(guild._chunks_left, guild.name))
        self._request_chunk(guild)

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

        if isinstance(event, (bytes, bytearray)):
            # decompress the message
            event = zlib.decompress(event, 15, 10490000)
            event = event.decode("utf-8")

        if event is None:
            return

        event_data = json.loads(event)
        # self.logger.debug("Got event {}".format(event_data))

        op = event_data.get('op')
        data = event_data.get('d')
        seq = event_data.get('s')

        if seq is not None:
            # next sequence
            self.sequence_num = seq

        # Switch based on op.
        if op == GatewayOp.HELLO:
            # Start heartbeating, with the specified heartbeat duration.
            heartbeat_interval = data.get("heartbeat_interval", 45000) / 1000.0
            self.logger.debug("Heartbeating every {} seconds.".format(heartbeat_interval))
            self._start_heartbeating(heartbeat_interval)

        elif op == GatewayOp.HEARTBEAT_ACK:
            self.heartbeat_acks += 1

        elif op == GatewayOp.HEARTBEAT:
            # Send a heartbeat back.
            hb = self._heartbeat_thread.get_heartbeat()
            self._send_json(hb)
            self.heartbeats += 1

        elif op == GatewayOp.INVALIDATE_SESSION:
            # Clean up our session.
            should_resume = data
            if should_resume is True:
                self.logger.debug("Sending RESUME again")
                self.send_resume()
            else:
                self.logger.warning("Received INVALIDATE_SESSION with d False, re-identifying.")
                self.sequence_num = 0
                self.state._reset(self.shard_id)
                self.send_identify()

        elif op == GatewayOp.RECONNECT:
            # Try and reconnect to the gateway.
            self._close()
            raise ReconnectWebsocket()

        elif op == GatewayOp.DISPATCH:
            # Handle the dispatch.
            event = event_data.get("t")
            handler = getattr(self.state, "handle_{}".format(event.lower()), None)

            if handler:
                # Invoke the handler, which will parse the data and update the cache internally.
                # Yes, handlers are async.
                # This is because curio requires `spawn()` to be async.
                try:
                    await handler(self, data)
                except ChunkGuild as e:
                    # We need to download all member chunks from this guild.
                    self._get_chunks(e.args[0])
                except Exception:
                    self.logger.exception("Error decoding {}".format(data))
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
