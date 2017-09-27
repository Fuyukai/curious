"""
A special gateway client for Voice.
"""
import enum
import json
import logging
import socket
import threading
import time
import typing
import zlib

import curio
from asyncwebsockets import Websocket, WebsocketBytesMessage, WebsocketClosed, connect_websocket
from curio.thread import AWAIT, async_thread

from curious.core.gateway import Gateway, ReconnectWebsocket

logger = logging.getLogger("curious.voice")

class VGatewayOp(enum.IntEnum):
    IDENTIFY = 0
    SELECT_PROTOCOL = 1
    READY = 2
    HEARTBEAT = 3
    SESSION_DESCRIPTION = 4
    SPEAKING = 5
    HEARTBEAT_ACK = 6
    HELLO = 8


@async_thread(daemon=True)
def _heartbeat_loop(gw: 'VoiceGateway', heartbeat_interval: float):
    """
    Heartbeat looper that loops and sends heartbeats to the gateway.

    :param gw: The gateway to handle.
    """
    # async threads!
    logger.debug("Sending initial heartbeat.")
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


class VoiceGateway(object):
    """
    A special type of websocket gateway that operates on the Voice connection.
    """

    GATEWAY_VERSION = 3

    def __init__(self, session_id: str, token: str, endpoint: str, user_id: str, guild_id: str):
        #: The current websocket object.
        self.websocket = None  # type: Websocket

        self._open = False

        self.session_id = session_id
        self.token = token
        self.user_id = user_id
        self.guild_id = guild_id
        self.sequence = 0
        self.ssrc_mapping = {}

        #: The main gateway object.
        self.main_gateway = None  # type: Gateway

        #: The current threading event used to signal if we need to stop heartbeating.
        self._stop_heartbeating = curio.Event()

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
        self.websocket = await connect_websocket(url)
        logger.info("Connected to gateway!")
        self._open = True
        return self.websocket

    async def _send(self, data):
        """
        Sends some data.

        This will actually send the data down the websocket, unlike `send` which only pretends to.
        """
        try:
            await self.websocket.send_message(data)
        except WebsocketClosed:
            await self._close()

    def get_heartbeat(self):
        """
        :return: A heartbeat packet.
        """
        return {
            "op": int(VGatewayOp.HEARTBEAT),
            # ms time for v2/v3
            "d": int(round(time.time() * 1000))
        }

    async def send_heartbeat(self):
        """
        Sends a heartbeat.
        """
        hb = self.get_heartbeat()
        return await self._send_json(hb)

    def _send_json(self, payload: dict):
        """
        Sends a JSON payload down the websocket.

        This is a private method - use :meth:`send` instead.

        :param payload: The payload to send.
        """
        data = json.dumps(payload)
        return self.send(data)

    async def send(self, data: typing.Any):
        """
        Enqueues some data to be sent down the websocket.
        """
        await self.websocket.send_message(data)

    # Sending methods
    async def send_identify(self):
        """
        Sends an IDENTIFY payload.
        """
        payload = {
            "op": VGatewayOp.IDENTIFY,
            "d": {
                "server_id": str(self.guild_id),
                "user_id": str(self.user_id),
                "session_id": str(self.session_id),
                "token": str(self.token)
            }
        }
        await self._send_json(payload)

    async def send_select_protocol(self, ip: str, port: int):
        """
        Sends a SELECT PROTOCOL packet.
        """
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

        await self._send_json(payload)

    async def send_speaking(self, speaking: bool = True):
        """
        Sends a SPEAKING packet.
        """
        payload = {
            "op": VGatewayOp.SPEAKING,
            "d": {
                "speaking": speaking,
                "delay": 0
            }
        }

        await self._send_json(payload)

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

    async def _close(self):
        if not self.websocket.closed:
            await self.websocket.close(code=1000, reason="Client disconnected")

        self._open = False
        await self._stop_heartbeating.set()

    @classmethod
    async def from_gateway(cls, gw: Gateway, guild_id: int, channel_id: int) -> 'VoiceGateway':
        """
        Opens a new voice gateway connection from an existing Gateway connection.

        :param gw: The existing :class:`.Gateway` to create from.
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
            await obb.connect(f"ws://{endpoint}/?v={cls.GATEWAY_VERSION}")
        elif port == "443":
            await obb.connect(f"wss://{endpoint}/?v={cls.GATEWAY_VERSION}")
        # Send our IDENTIFY.
        logger.info("Sending IDENTIFY...")
        await obb.send_identify()

        return obb

    async def next_event(self) -> None:
        """
        Gets the next event, in decoded form.
        """
        if not self._open:
            raise WebsocketClosed(1006, reason="Connection lost")

        try:
            event = await self.websocket.next_message()
        except WebsocketClosed:
            # Close ourselves.
            await self._close()
            raise

        if isinstance(event, WebsocketBytesMessage):
            # decompress the message
            data = zlib.decompress(event.data, 15, 10490000)
            data = data.decode("utf-8")
        else:
            data = event.data

        if data is None:
            return

        event = json.loads(data)

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
            await self._start_heartbeating(heartbeat_interval)
            # Set our `ssrc`, `port` and `modes`.
            self.ssrc = data.get("ssrc")
            self.port = data.get("port")

            await self._ready.set()

        elif op == VGatewayOp.SESSION_DESCRIPTION:
            # Extract the secret key.
            self.secret_key = data["secret_key"]
            await self.send_speaking()
            await self._got_secret_key.set()

        elif op == VGatewayOp.SPEAKING:
            # build a cache of user_id -> ssrc
            user_id = int(data.get("user_id"))
            ssrc = data.get("ssrc")
            self.ssrc_mapping[ssrc] = user_id

        elif op == VGatewayOp.HEARTBEAT:
            # silence
            pass

        elif op == VGatewayOp.HEARTBEAT_ACK:
            # suppress
            pass

        else:
            logger.warning("Unhandled event: {}".format(op))
