"""
A special gateway client for Voice.
"""
import enum
import json
import logging
import queue
import socket
import threading
import zlib

import curio
import typing
from cuiows.client import WSClient
from cuiows.exc import WebsocketClosedError

from curious.core.gateway import Gateway


class VGatewayOp(enum.IntEnum):
    IDENTIFY = 0
    SELECT_PROTOCOL = 1
    READY = 2
    HEARTBEAT = 3
    SESSION_DESCRIPTION = 4
    SPEAKING = 5
    HELLO = 8


class _HeartbeatThread(threading.Thread):
    """
    A subclass of threading.Thread that sends heartbeats every <x> seconds.
    """

    def __init__(self, gw: 'VoiceGateway', heartbeat_interval: float, *args, **kwargs):
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
            "op": int(VGatewayOp.HEARTBEAT),
            "d": self._gateway.sequence
        }

    def _send_heartbeat(self):
        hb = self.get_heartbeat()

        # Enqueue onto the sending queue.
        logger.debug("Voice session heartbeating with sequence {}".format(hb["d"]))
        self._gateway.send(hb)


logger = logging.getLogger("curious.voice")


class VoiceGateway(object):
    """
    A special type of websocket gateway that operates on the Voice connection.
    """

    def __init__(self, session_id: str, token: str, endpoint: str, user_id: str, guild_id: str):
        #: The current cuiows websocket object.
        self.websocket = None  # type: WSClient

        self._open = False

        self.session_id = session_id
        self.token = token
        self.user_id = user_id
        self.guild_id = guild_id
        self.sequence = 0

        #: The main gateway object.
        self.main_gateway = None  # type: Gateway

        #: The event queue.
        self._event_queue = queue.Queue()

        #: The sender task.
        self._sender_task = None  # type: curio.Task

        #: The current heartbeat thread.
        self._heartbeat_thread = None

        #: Voice server stuff
        self.endpoint = endpoint
        self.port = None  # type: int
        self.ssrc = None  # type: int
        self.secret_key = b""

        self._ready = curio.Event()
        self._got_secret_key = curio.Event()

    async def connect(self, url: str):
        """
        Connects the client to the websocket.

        This does not do ANY handshake steps.
        :param url: The URL to connect to.
        """
        logger.info("Opening connection to {}".format(url))
        self.websocket = await WSClient.connect(url)
        logger.info("Connected to gateway!")
        self._open = True
        return self.websocket

    # copied from main gateway
    async def _send_events(self):
        while self._open:
            try:
                next_item = await curio.abide(self._event_queue.get)
            except curio.CancelledError:
                self._event_queue.put_nowait(next_item)
                return
            if isinstance(next_item, dict):
                # this'll come back around in a sec
                self._send_json(next_item)
            else:
                logger.debug("Sending websocket data {}".format(next_item))
                await self._send(next_item)

    async def _send(self, data):
        """
        Sends some data.

        This will actually send the data down the websocket, unlike `send` which only pretends to.
        """
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

    # Sending methods
    def send_identify(self):
        payload = {
            "op": VGatewayOp.IDENTIFY,
            "d": {
                "server_id": str(self.guild_id),
                "user_id": str(self.user_id),
                "session_id": str(self.session_id),
                "token": str(self.token)
            }
        }
        self._send_json(payload)

    def send_select_protocol(self, ip: str, port: int):
        payload = {
            "op": VGatewayOp.SELECT_PROTOCOL,
            "d": {
                "protocol": "udp",
                "data": {
                    "address": ip,
                    "port": port,
                    "mode": "xsalsa20_poly1305"
                }
            }
        }

        self._send_json(payload)

    def send_speaking(self, speaking: bool=True):
        payload = {
            "op": VGatewayOp.SPEAKING,
            "d": {
                "speaking": speaking,
                "delay": 0
            }
        }

        self._send_json(payload)

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

    async def _close(self):
        if not self.websocket.closed:
            await self.websocket.close_now(code=1000, reason="Client disconnected")

        self._open = False
        self._heartbeat_thread._stop_heartbeating.set()
        await self._sender_task.cancel()
        # put something on the queue to kill the old task
        self._event_queue.put(None)
        del self._event_queue

    @classmethod
    async def from_gateway(cls, gw: Gateway, guild_id: int, channel_id: int) -> 'VoiceGateway':
        """
        Opens a new voice gateway connection from an existing Gateway connection.

        :param gw: The existing :class:`Gateway` to create from.
        :param guild_id: The guild ID we're opening to.
        :param channel_id: The channel ID we're connecting to.
        """
        # Send our VOICE_STATE_UPDATE to tell Discord to start connecting us to voice.
        await gw.send_voice_state_update(guild_id, channel_id)
        state = await gw.state.wait_for_voice_data(guild_id)
        user_id = gw.state._user.id

        # Look up the gateway's IP address.
        endpoint = state["endpoint"]
        endpoint, port = endpoint.split(":")
        endpoint = await curio.abide(socket.gethostbyname, endpoint)

        obb = cls(token=state["token"], session_id=state["session_id"],
                  endpoint=endpoint,
                  user_id=user_id, guild_id=guild_id)
        # Open our connection to the voice websocket.
        if port == "80":
            await obb.connect("ws://{}".format(state["endpoint"]))
        elif port == "443":
            await obb.connect("ws://{}".format(state["endpoint"]))
        obb._sender_task = await curio.spawn(obb._send_events())
        # Send our IDENTIFY.
        obb.send_identify()

        return obb

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

        event = json.loads(event)

        op = event.get("op")
        data = event.get("d")
        seq = event.get("seq")

        # Heartbeat logic, same as normal websocket
        if seq is not None:
            self.sequence = int(seq)

        # Switch based on operator.
        if op == VGatewayOp.HELLO:
            # Ignore these, they're useless for now.
            return

        elif op == VGatewayOp.READY:
            # Start heartbeating.
            heartbeat_interval = data.get("heartbeat_interval", 45000) / 1000.0
            logger.debug("Heartbeating every {} seconds.".format(heartbeat_interval))
            self._start_heartbeating(heartbeat_interval)
            # Set our `ssrc`, `port` and `modes`.
            self.ssrc = data.get("ssrc")
            self.port = data.get("port")

            await self._ready.set()

        elif op == VGatewayOp.SESSION_DESCRIPTION:
            # Extract the secret key.
            self.secret_key = data.get('secret_key')
            self.send_speaking()
            await self._got_secret_key.set()

        elif op == VGatewayOp.HEARTBEAT:
            # silence
            pass

        else:
            logger.warning("Unhandled event: {}".format(op))
