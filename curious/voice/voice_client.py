"""
Represents a voice client.

Other documentation:

- Timestamp increases by 48 * 20 every time (samples * frame length).
- Sequence and timestamp both overflow.

frame_length = 20 (??)
sample_size = 4 (2 * 2)
samples_per_frame: 48 * 20
frame_size = samples_per_frame APPARENTLY


"""
import logging
import socket
import struct

import curio
from nacl.secret import SecretBox
from opuslib import Encoder

from curious.voice import voice_player as vp
from curious.voice.voice_gateway import VoiceGateway

logger = logging.getLogger("curious.voice")


def simulate_overflow(value: int, bits: int, signed: bool):
    """
    Simulates integer overflow.
    """
    base = 1 << bits
    value %= base
    return value - base if signed and value.bit_length() == bits else value


class VoiceClient(object):
    """
    The voice client instance controls connecting to Discord's voice servers.

    This should ***not*** be created directly - instead use :class:`~.Channel.connect()` to connect to a voice channel,
    and use the instance returned from.
    """

    def __init__(self, main_client,
                 channel):
        """
        :param main_client: The :class:`~.curious.core.client.Client` object associated with this VoiceClient. 
        :param channel: The :class:`~.Channel` associated with this VoiceClient.
        """

        #: The main client this voice client is associated with.
        self.client = main_client

        #: The voice channel this client is connected to.
        self.channel = channel

        #: The voice websocket that we are connected to.
        self.vs_ws = None  # type: VoiceGateway

        #: The UDP socket that we are connected to.
        self._sock = None  # type: socket.socket

        self.main_task = None  # type: curio.Task

        # Header related stuff
        self.sequence = 0  # sequence is 2 bytes
        self.timestamp = 0  # timestamp is 4 bytes

        self.encoder = Encoder(48000, 2, 'audio')
        self.encoder.bitrate = 96000

    @property
    def open(self):
        return self.vs_ws._open

    # Voice encoder related things.
    def _get_packet_header(self):
        header = bytearray(12)

        # constant values, provided by the docs
        header[0:2] = b"\x80\x78"

        # dynamic values
        # offset 2 -> sequence
        struct.pack_into(">H", header, 2, self.sequence)
        # offset 4 -> timestamp
        struct.pack_into(">I", header, 4, self.timestamp)
        # offset 8 -> ssrc
        struct.pack_into(">I", header, 8, self.vs_ws.ssrc)

        return header

    def _get_voice_packet(self, opus_body: bytes):
        header = self._get_packet_header()
        nonce = bytearray(24)
        # copy the header into nonce
        nonce[:12] = header

        encryptor = SecretBox(bytes(self.vs_ws.secret_key))
        encrypted_body = encryptor.encrypt(opus_body, nonce=bytes(nonce))

        # pack_nonce is True, so the body can just be concatted
        return bytes(header + encrypted_body.ciphertext)

    def _get_ip_discovery_packet(self):
        packet = bytearray(70)
        packet[0:4] = struct.pack(">I", self.vs_ws.ssrc)

        return packet

    def _send_voice_packet(self, built_packet: bytes):
        """
        Sends a voice packet.

        :param built_packet: The final built packet, as got by `_get_voice_packet`.
        """
        # Overflow values as appropriate.
        sequence = self.sequence + 1
        self.sequence = simulate_overflow(sequence, 2 * 8, False)

        timestamp = self.timestamp + (20 * 48)
        self.timestamp = simulate_overflow(timestamp, 2 * 16, False)

        try:
            self._sock.sendto(built_packet, (self.vs_ws.endpoint, self.vs_ws.port))
        except BlockingIOError:
            # can't send rn, oh well
            # opus is built for this
            logger.error("Failed to send voice packet! Sequence: {}, timestamp: {}".format(self.sequence,
                                                                                           self.timestamp))

    def send_opus_data(self, opus_data: bytes):
        """
        Sends an opus-encoded voice packet.

        :param opus_data: The data to send.
        """
        packet = self._get_voice_packet(opus_data)
        self._send_voice_packet(packet)

    def send_voice_packet(self, voice_data: bytes):
        """
        Sends voice data from a PCM buffer.

        :param voice_data: The raw PCM voice data to send.
        """
        data = self.encoder.encode(voice_data, 960)
        self.send_opus_data(data)

    def play_path(self, path: str):
        """
        Plays a file using ffmpeg.
        """
        player = vp.VoicePlayer(self, path)
        player.start()

    async def poll(self):
        """
        Polls the voice websocket constantly for new events.
        """
        while True:
            await self.vs_ws.next_event()

    async def close(self):
        await self.vs_ws._close()
        await self.main_task.cancel()

    async def connect(self, timeout=10):
        """
        Connects the voice client to the UDP server.
        """
        logger.info("Opening UDP connection to Discord voice servers.")
        # Wait before the voice socket is ready.
        await self.vs_ws._ready.wait()
        # Open our UDP connection.
        # TODO: Make this IPv6 compatible, if appropriate.
        # Now, you may be wondering why we use raw UDP sockets instead of using "nice" sockets.
        # This is because we need a voice thread to be able to access it.
        # This prevents blocking actions from killing the entire voice connection.
        addrinfo = await curio.abide(socket.getaddrinfo, self.vs_ws.endpoint, self.vs_ws.port,
                                     type=socket.SOCK_DGRAM)

        for item in addrinfo:
            try:
                new_socket = socket.socket(item[0], item[1])
                break
            except:
                continue
        else:
            raise ConnectionError("Could not create voice socket")

        self._sock = new_socket

        # Send an IP discovery packet.
        logger.info("Connecting to {}:{}".format(self.vs_ws.endpoint, self.vs_ws.port))
        packet = self._get_ip_discovery_packet()
        logger.debug("Sending IP discovery packet")
        self._sock.sendto(packet, (self.vs_ws.endpoint, self.vs_ws.port))

        # Wait for our local IP to be received.
        try:
            packet_data, addr = await curio.timeout_after(timeout, curio.abide(self._sock.recvfrom, 70))
        except curio.TaskTimeout:
            self._sock.close()
            self.vs_ws._close()
            raise
        logger.debug("Got IP discovery packet!")

        # IP is encoded in ASCII, from the forth byte to the first \x00 byte.
        # Find the index of the null byte, starting from 4th.
        ip_start = 4
        ip_end = packet_data.index(0, ip_start)

        our_ip = packet_data[ip_start:ip_end].decode('ascii')
        # Also, we need our local port.
        # Unpack the little-endian (thanks discord!) port from the very end of the voice packet.
        our_port = struct.unpack_from('<H', packet_data, len(packet_data) - 2)[0]

        # Ask the voice websocket to send our SESSION DESCRIPTION packet.
        self.vs_ws.send_select_protocol(our_ip, our_port)
        await self.vs_ws._got_secret_key.wait()
        logger.info("Established connection to Discord's voice servers.")

        self._sock.setblocking(False)

        # We are DONW!

    @classmethod
    async def create(cls, main_client,
                     gateway, channel) -> 'VoiceClient':
        """
        Creates a new VoiceClient from a channel and a gateway instance.

        :param gateway: The gateway instance to use.
        :param channel: The :class:`~.Channel` to connect to.
        """
        vs_ws = await VoiceGateway.from_gateway(gw=gateway, channel_id=channel.id, guild_id=channel.guild.id)
        obb = cls(main_client, channel=channel)
        obb.vs_ws = vs_ws
        obb.main_task = await curio.spawn(obb.poll())
        return obb
