"""
Websocket gateway code.
"""
import enum
import json
import threading
import typing
import queue
import sys
import logging
import zlib
from math import ceil

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
        while not self._stop_heartbeating.wait(self._hb_interval):
            hb = self.get_heartbeat()

            # Enqueue onto the sending queue.
            self._gateway.send(hb)

            self._gateway.heartbeats += 1

    def get_heartbeat(self):
        """
        :return: A heartbeat packet.
        """
        return {
            "op": int(GatewayOp.HEARTBEAT),
            "d": self._gateway.sequence_num
        }


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
        self.logger = logging.getLogger("curious.gateway")

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

        # Heartbeats and ACKs are tracked by this class to make sure if we send a heartbeat, but the previous one has
        #  not been ACK'd yet, we need to reconnect, as we've lost connection.
        #: The number of heartbeats this connection has sent.
        self.heartbeats = 0

        #: The number of heartbeat ACKs this connection has sent.
        self.heartbeat_acks = 0

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
            next_item = await curio.abide(self._event_queue.get)
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
        await self.websocket.send(data)

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
        """
        try:
            self._event_queue.put(data, block=False)
        except queue.Full as e:
            # what the fuck?
            # Don't fucking touch my queue!
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
                "v": 6
            }
        }

        # TODO: Sharding
        self._send_json(payload)

    def send_resume(self):
        """
        Sends a RESUME packet.
        """
        payload = {
            "op": GatewayOp.RESUME,
            "d": {
                "token": self.token,
                "session_id": self.state._session_id,
                "seq": self.sequence_num
            }
        }

        self._send_json(payload)

    def send_status(self, game: Game, status: Status):
        payload = {
            "op": GatewayOp.PRESENCE,
            "d": {
                "game": game.to_dict() if game else None,
                "status": status.name,
                "afk": False,
                "since": None
            }
        }
        self._send_json(payload)

    async def _request_chunk(self, guild):
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
    async def from_token(cls, token: str, state: State, gateway_url: str) -> 'Gateway':
        """
        Creates a new gateway connection from a token.

        :param token: The token to pass in.
            This must be a bot user token - user tokens are not supported.
        :return: A new :class:`Gateway` that is connected to the API.
        """
        obb = cls(token, state)

        gateway_url += "?v={}&encoding=json".format(cls.GATEWAY_VERSION)
        obb._cached_gateway_url = gateway_url

        await obb.connect(gateway_url)

        # Create the event sender task.
        obb._event_reader = await curio.spawn(obb._send_events())

        # send IDENTIFY
        obb.logger.info("Sending IDENTIFY...")
        obb.send_identify()

        return obb

    async def reconnect(self, *, resume: bool=False):
        """
        Reconnects the bot to the gateway.

        :param resume: Should a RESUME be attempted?
        """
        self.logger.info("Reconnecting to the gateway")
        if not self.websocket.closed:
            await self.websocket.close_now()

        self._open = False

        await self.connect(self._cached_gateway_url)
        self._event_reader = await curio.spawn(self._send_events())

        if resume:
            # Send the RESUME packet, instead of the IDENTIFY packet.
            self.logger.info("Sending RESUME...")
            self.send_resume()
        else:
            self.logger.info("Sending IDENTIFY...")
            self.send_identify()

        return self

    async def _get_chunks(self, guild):
        """
        Called to start chunking all guild members.
        """
        guild.start_chunking()
        await self._request_chunk(guild)

    async def next_event(self):
        """
        Gets the next event, in decoded form.
        """
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
            await self._send_json(hb)
            self.heartbeats += 1

        elif op == GatewayOp.INVALIDATE_SESSION:
            # Clean up our session.
            self.sequence_num = 0
            self.state._reset()
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
                    await handler(data)
                except ChunkGuild as e:
                    # We need to download all member chunks from this guild.
                    await curio.spawn(self._get_chunks(e.args[0]))
                except Exception:
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
