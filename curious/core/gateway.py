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
Code that wraps the Discord gateway connection.
"""
import enum
import json
import logging
import ssl
import sys
import time
import zlib
from dataclasses import dataclass
from typing import Optional

import trio
from trio import CancelScope, SocketStream
from trio_websocket import WebSocketConnection, wrap_client_stream, ConnectionClosed
from trio_websocket._impl import _url_to_host


class GatewayOp(enum.IntEnum):
    """
    A mapping of possible gateway operation codes.
    """

    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE = 3
    VOICE_STATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_MEMBERS = 8
    INVALIDATE_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11


@dataclass
class GatewayInfo:
    """
    Wraps various state information for the current gateway.
    """

    #: The current token.
    token: str

    #: The current gateway URL.
    gateway_url: str

    #: The shard ID for this gateway.
    shard_id: int

    #: The shard count for this gateway.
    shard_count: int

    #: The current session ID.
    session_id: str = None

    #: The current sequence.
    sequence: int = 0

    #: The intents that should be used.
    intents: int = 0


@dataclass
class HeartbeatStats:
    """
    Represents the statistics for the gateway's heartbeat counters.
    """

    #: The number of heartbeats sent.
    heartbeats: int = 0

    #: The number of heartbeat acks received.
    heartbeat_acks: int = 0

    #: Internal time when the last heartbeat was sent.
    last_heartbeat_time: int = 0

    #: Internal time when the last heartbeat_ack was received.
    last_ack_time: int = 0

    @property
    def gw_time(self) -> float:
        """
        :return: The time the most recent heartbeat and heartbeat_ack.
        """
        return self.last_ack_time - self.last_heartbeat_time


@dataclass
class WebsocketWrapper:
    """
    A wrapper class that lets us directly close the underlying TCP stream, to prevent deadlocks.
    """

    stream: SocketStream
    websocket: WebSocketConnection


class GatewayIntent(enum.IntEnum):
    """
    Enumeration of possible gateway intents.
    """

    GUILDS = 1
    GUILD_MEMBERS = 1 << 1
    GUILD_BANS = 1 << 2
    GUILD_EMOJIS = 1 << 3
    GUILD_INTEGRATIONS = 1 << 4
    GUILD_WEBHOOKS = 1 << 5
    GUILD_INVITES = 1 << 6
    GUILD_VOICE_STATES = 1 << 7
    GUILD_PRESENCES = 1 << 8
    GUILD_MESSAGES = 1 << 9
    GUILD_MESSAGE_REACTIONS = 1 << 10
    GUILD_MESSAGE_TYPING = 1 << 11
    DIRECT_MESSAGES = 1 << 12
    DIRECT_MESSAGE_REACTIONS = 1 << 13
    DIRECT_MESSAGE_TYPING = 1 << 14


# TODO: Now that I think about this, this might be done better as just one big function.
#       The class design was fine in the original Curio version, but maybe not this one...


class GatewayHandler(object):
    """
    Primary class that handles connecting to the Discord gateway.
    """

    GATEWAY_VERSION = 8
    ZLIB_FLUSH_SUFFIX = b"\x00\x00\xff\xff"

    def __init__(
        self,
        token: str,
        gateway_url: str,
        shard_id: int,
        shard_count: int,
        intents_bitfield: int = None,
    ):
        if intents_bitfield is None:
            intents_bitfield = (
                GatewayIntent.GUILDS
                | GatewayIntent.GUILD_MEMBERS
                | GatewayIntent.GUILD_BANS
                | GatewayIntent.GUILD_EMOJIS
                | GatewayIntent.GUILD_INVITES
                | GatewayIntent.GUILD_PRESENCES
                | GatewayIntent.GUILD_MESSAGES
                | GatewayIntent.GUILD_MESSAGE_REACTIONS
                | GatewayIntent.DIRECT_MESSAGES
                | GatewayIntent.DIRECT_MESSAGE_REACTIONS
            )

        gateway_url = gateway_url + f"/?v={self.GATEWAY_VERSION}&encoding=json&compress=zlib-stream"
        self.info = GatewayInfo(
            token=token,
            gateway_url=gateway_url,
            shard_id=shard_id,
            shard_count=shard_count,
            intents=intents_bitfield,
        )
        self.heartbeat_stats = HeartbeatStats()

        self._logger: Optional[logging.Logger] = None

        self._last_ws_connection: Optional[WebsocketWrapper] = None

        # used in the reconnect loop. does not reflect the actual state of the websocket.
        self._is_open: bool = True
        # overall nursery cancel scope
        self._last_cancel_scope: Optional[CancelScope] = None
        self._heartbeat_cancel_scope: Optional[CancelScope] = None

        # used for zlib-streaming
        self._databuffer = bytearray()
        self._decompressor = zlib.decompressobj()

    @property
    def logger(self) -> logging.Logger:
        if self._logger:
            return self._logger

        self._logger = logging.getLogger("curious.gateway:shard-{}".format(self.info.shard_id))
        return self._logger

    def reset(self):
        self.info.session_id = None
        self.info.sequence = 0
        self.heartbeat_stats.heartbeats = 0
        self.heartbeat_stats.heartbeat_acks = 0

    async def _close(self, code: int = 1000, reason: str = "Websocket closing"):
        """
        Closes the current websocket connection.
        """
        if self._heartbeat_cancel_scope is not None:
            self._heartbeat_cancel_scope.cancel()

        self.heartbeat_stats = HeartbeatStats()

        if self._last_ws_connection is None:
            return

        try:
            with trio.fail_after(5):
                await self._last_ws_connection.websocket.aclose(code=code, reason=reason)
        except trio.TooSlowError:
            # just forcibly nuke the stream
            await self._last_ws_connection.stream.aclose()
        finally:
            self._last_ws_connection = None

    async def _connect(self, nursery: trio.Nursery):
        """
        Connects the websocket to the gateway. This ONLY connects the actual socket.
        """
        await self._close()
        self._databuffer.clear()
        self._decompressor = zlib.decompressobj()

        # yikes!
        host, port, resource, ssl_context = _url_to_host(self.info.gateway_url, None)
        self.logger.debug(f"Opening TCP connection to {host}:{port}/{resource}")

        # TODO: Make the timeout configurable?
        with trio.fail_after(30):
            if not ssl_context:
                stream = await trio.open_tcp_stream(host, port)
            else:
                stream = await trio.open_ssl_over_tcp_stream(
                    host, port, https_compatible=True, ssl_context=ssl.create_default_context()
                )

            wss = await wrap_client_stream(nursery, stream, host, resource)

        stream = WebsocketWrapper(stream, wss)
        self._last_ws_connection = stream

    async def _send_heartbeat(self) -> None:
        """
        Sends a heartbeat to Discord.
        """
        if self.heartbeat_stats.heartbeats > self.heartbeat_stats.heartbeat_acks + 1:
            self.logger.warning("Connection has zombied, reconnecting.")

            # Note: The 1006 close code signifies an error.
            # In my testing, closing with a 1006 will allow a resume once reconnected,
            # whereas other close codes won't.
            # The timeout mihgt be too high to RESUME, however.
            return await self._close(code=1006, reason="Zombied connection")

        self.logger.debug(
            f"Sending heartbeat #{self.heartbeat_stats.heartbeats} with sequence "
            f"{self.info.sequence}"
        )
        payload = {"op": GatewayOp.HEARTBEAT, "d": self.info.sequence}
        await self.send(payload)
        self.heartbeat_stats.heartbeats += 1
        self.heartbeat_stats.last_heartbeat_time = time.monotonic()

    async def _heartbeat_loop(self, interval: float):
        """
        Loops sending heartbeats.
        """
        with trio.CancelScope() as scope:
            self._heartbeat_cancel_scope = scope

            while True:
                await self._send_heartbeat()
                await trio.sleep(interval)

    async def _send_identify(self) -> None:
        """
        Sends an IDENTIFY to Discord.
        """
        payload = {
            "op": GatewayOp.IDENTIFY,
            "d": {
                "token": self.info.token,
                "properties": {
                    "$os": sys.platform,
                    "$browser": "curious",
                    "$device": "curious",
                    "$referrer": "",
                    "$referring_domain": "",
                },
                "large_threshold": 250,
                "v": self.GATEWAY_VERSION,
                "shard": [self.info.shard_id, self.info.shard_count],
                "intents": self.info.intents,
            },
        }
        return await self.send(payload)

    async def _send_resume(self) -> None:
        """
        Sends the RESUME packet.
        """
        payload = {
            "op": GatewayOp.RESUME,
            "d": {
                "token": self.info.token,
                "session_id": self.info.session_id,
                "seq": self.info.sequence,
            },
        }

        return await self.send(payload)

    async def send(self, data: dict) -> None:
        """
        Sends data down the websocket.
        """
        dumped = json.dumps(data)
        return await self._last_ws_connection.websocket.send_message(dumped)

    async def kill(self, code: int = 1006, reason: str = "Abnormal termination"):
        """
        Kills the gateway gracefully.
        """
        self._is_open = False
        self.logger.warning("Forcibly killing the gateway connection.")
        if self._last_cancel_scope is not None:
            self._last_cancel_scope.cancel()

        await self._close(code=code, reason=reason)

    async def read_events(self):
        """
        Reads off events from the websocket. This is an asynchronous generator.
        """
        async with trio.open_nursery() as nursery:
            self._last_cancel_scope = nursery.cancel_scope

            while self._is_open:
                await self._connect(nursery)

                while True:
                    try:
                        next_event = await self._last_ws_connection.websocket.get_message()
                    except ConnectionClosed:
                        break

                    # annoying zlib compression...
                    if isinstance(next_event, bytes):
                        self._databuffer.extend(next_event)
                        if not next_event.endswith(self.ZLIB_FLUSH_SUFFIX):
                            return
                        else:
                            data = self._decompressor.decompress(self._databuffer).decode("utf-8")
                            self._databuffer.clear()
                    else:
                        data = next_event

                    # empty payloads
                    if not data:
                        return

                    decoded = json.loads(data)
                    opcode = decoded.get("op")
                    sequence = decoded.get("s")
                    if sequence is not None:
                        self.info.sequence = sequence

                    event_data = decoded.get("d", {})

                    # the grand old opcode switch
                    if opcode == GatewayOp.HELLO:
                        heartbeat_interval = event_data.get("heartbeat_interval", 45000) / 1000.0

                        self.logger.debug(f"Heartbeating every {heartbeat_interval} seconds.")
                        nursery.start_soon(self._heartbeat_loop, heartbeat_interval)

                        trace = ", ".join(event_data["_trace"])
                        self.logger.info(f"Connected to Discord servers {trace}")

                        if self.info.session_id is None:
                            await self._send_identify()
                        else:
                            await self._send_resume()

                        yield "gateway_hello", event_data["_trace"]

                    elif opcode == GatewayOp.HEARTBEAT:
                        await self._send_heartbeat()
                        yield "gateway_heartbeat_received",

                    elif opcode == GatewayOp.HEARTBEAT_ACK:
                        self.heartbeat_stats.heartbeat_acks += 1
                        self.heartbeat_stats.last_ack_time = time.monotonic()
                        self.logger.debug(
                            f"Recevied heartbeat ack #{self.heartbeat_stats.heartbeat_acks}"
                        )
                        yield "gateway_heartbeat_ack",

                    elif opcode == GatewayOp.INVALIDATE_SESSION:
                        should_resume = data or False

                        if should_resume:
                            await self._send_resume()
                        else:
                            self.reset()
                            await self._send_identify()

                        yield "gateway_invalidate_session", should_resume

                    elif opcode == GatewayOp.RECONNECT:
                        await self._close(code=1000, reason="Connection closing")
                        yield "gateway_reeconnect",
                        break

                    elif opcode == GatewayOp.DISPATCH:
                        event = decoded.get("t")
                        if not event:
                            continue

                        if event == "READY":
                            self.info.session_id = event_data["session_id"]

                        yield "gateway_dispatch_received", event, event_data

                    else:
                        raise ValueError(f"Received unhandled opcode {opcode}")
