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
import heapq
import logging
import socket
import struct
import time
from io import BytesIO
from typing import Tuple, Union

import curio
from curio.io import Socket
from curio.socket import getaddrinfo
from nacl.secret import SecretBox
from opuslib import Decoder, Encoder
from opuslib.exceptions import OpusError

from curious.dataclasses import member as dt_member, user as dt_user
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

    This should ***not*** be created directly - instead use :class:`~.Channel.connect()` to connect
    to a voice channel, and use the instance returned from.
    """

    def __init__(self, main_client,
                 channel):
        """
        :param main_client: The :class:`~.curious.core.client.Client` object associated with this
            VoiceClient.
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

        # Opus encoder/decoder
        # Do not use
        self.encoder = Encoder(48000, 2, 'audio')
        self.encoder.bitrate = 96000
        self.decoder = Decoder(48000, 2)

    @property
    def open(self):
        return self.vs_ws._open

    # Voice encoder related things.
    def get_packet_header(self) -> bytes:
        """
        Gets the voice packet header.

        :return: The bytes of the header.
        """
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

    def get_voice_packet(self, opus_body: bytes) -> bytes:
        """
        Gets the voice packet to send to Discord, after encryption.

        :param opus_body: The body of the packet to encrypt.
        :return: The bytes of the packet.
        """
        header = self.get_packet_header()
        nonce = bytearray(24)
        # copy the header into nonce
        nonce[:12] = header

        encryptor = SecretBox(bytes(self.vs_ws.secret_key))
        encrypted_body = encryptor.encrypt(opus_body, nonce=bytes(nonce))

        # pack_nonce is True, so the body can just be concatted
        return bytes(header + encrypted_body.ciphertext)

    def get_ip_discovery_packet(self) -> bytes:
        """
        Gets the IP discovery packet to send to Discord.
        """
        packet = bytearray(70)
        packet[0:4] = struct.pack(">I", self.vs_ws.ssrc)

        return packet

    def unpack_packet(self, data: bytes) -> Tuple[int, int, int, bytes]:
        """
        Unpacks a voice packet received from Discord.

        :param data: The data to unpack.
        :return: A tuple of (ssrc, sequence, timestamp, data).
        """
        header = data[:12]
        encrypted_data = data[12:]

        # unpack header data
        type_ = header[0]
        version = header[1]
        sequence = struct.unpack(">H", header[2:4])[0]
        timestamp = struct.unpack(">I", header[4:8])[0]
        ssrc = struct.unpack(">I", header[8:12])[0]

        # okay, for some reason discord sends malformed packets
        # 0x90 as type means we need to chop off the first 8 bytes from the decrypted data
        # because it's invalid opus
        # first, decrypt the data

        nonce = bytearray(24)
        nonce[:12] = header

        encryptor = SecretBox(bytes(self.vs_ws.secret_key))
        decrypted = encryptor.decrypt(encrypted_data, nonce=bytes(nonce))

        if type_ == 0x90:
            decrypted = decrypted[8:]

        pcm_frames = self.decoder.decode(decrypted, 3840)

        return ssrc, sequence, timestamp, pcm_frames

    def _send_voice_packet(self, built_packet: bytes):
        """
        Sends a voice packet.

        :param built_packet: The final built packet, as got by :meth:`.get_voice_packet`.
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
            logger.error("Failed to send voice packet! Sequence: {}, timestamp: {}".
                         format(self.sequence, self.timestamp))

    def send_opus_data(self, opus_data: bytes):
        """
        Sends an opus-encoded voice packet.

        :param opus_data: The data to send.
        """
        packet = self.get_voice_packet(opus_data)
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
        """
        Closes the websocket. 
        """
        await self.vs_ws._close()
        await self.main_task.cancel()

    async def connect(self, timeout: int = 10) -> None:
        """
        Connects the voice client to the UDP server.

        :param timeout: The timeout before the connection is closed.
        """
        logger.info("Opening UDP connection to Discord voice servers.")
        # Wait before the voice socket is ready.
        await self.vs_ws._ready.wait()
        # Open our UDP connection.
        # TODO: Make this IPv6 compatible, if appropriate.
        # Now, you may be wondering why we use raw UDP sockets instead of using "nice" sockets.
        # This is because we need a voice thread to be able to access it.
        # This prevents blocking actions from killing the entire voice connection.

        addrinfo = await getaddrinfo(self.vs_ws.endpoint,
                                     self.vs_ws.port,
                                     0,
                                     socket.SOCK_DGRAM)

        for item in addrinfo:
            try:
                new_socket = socket.socket(item[0], item[1])
                break
            except:
                logger.debug("Failed to make socket", exc_info=True)
        else:
            raise ConnectionError("Could not create voice socket")

        self._sock = new_socket

        # Send an IP discovery packet.
        logger.info("Connecting to {}:{}".format(self.vs_ws.endpoint, self.vs_ws.port))
        packet = self.get_ip_discovery_packet()
        logger.debug("Sending IP discovery packet")
        self._sock.sendto(packet, (self.vs_ws.endpoint, self.vs_ws.port))

        # Wait for our local IP to be received.
        try:
            packet_data, addr = await curio.timeout_after(timeout,
                                                          curio.abide(self._sock.recvfrom, 70))
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
        await self.vs_ws.send_select_protocol(our_ip, our_port)
        await self.vs_ws._got_secret_key.wait()
        logger.info("Established connection to Discord's voice servers.")

        self._sock.setblocking(False)

        # We are DONW!

    async def receive_voice_data(self, author: 'Union[dt_user.User, dt_member.Member]',
                                 start_timeout: int = 2000,
                                 end_timeout: int = 500) -> BytesIO:
        """
        Receives voice data from the specified author.

        This will automatically re-order any voice packets by their ``sequence`` field in the
        header.

        .. warning::

            Only one call of this can be done per voice client at any given time.

        :param author: The author to listen to. None to listen to ALL audio.
        :param start_timeout: The number of ms to wait for the first UDP packets.
        :param end_timeout: The number of ms to wait after a packet has been received to return.
        :return: A :class:`BytesIO` with the data written to it.
        """
        # human explanation of what this does
        # 1) it reads data from the UDP socket
        # 2) it decodes the header, and body
        # 3) it checks the ssrc, and if it matches with the one we have cached, we put it in the
        #    heap ordered based on sequence
        # 4) once no udp packets have been received in the last <timeout> ms, we join all the
        #    data together and return
        packet_heap = []
        last_packet = 0

        # wrap the socket in an io.Socket so we dont spam threads
        sock = Socket(self._sock)

        while True:
            # check if it's been more than end_timeout ms and we've started to receive packets
            if last_packet > 0 and (time.monotonic() - last_packet) >= end_timeout:
                break

            try:
                timeout = end_timeout if last_packet > 0 else start_timeout
                data = await curio.timeout_after(timeout / 1000, sock.recv(8192))
            except curio.TaskTimeout:
                # no data was received, so we need to timeout.
                break

            try:
                ssrc, sequence, timestamp, data = self.unpack_packet(data)
            except OpusError:
                # malformed packet
                continue

            # ensure we dont have useless data
            if ssrc not in self.vs_ws.ssrc_mapping:
                continue

            # check we're listening to the packet for the right author
            if author is not None:
                if author.id != self.vs_ws.ssrc_mapping[ssrc]:
                    continue

            item = (sequence, timestamp, data)
            heapq.heappush(packet_heap, item)

        body = BytesIO()
        for i in range(len(packet_heap)):
            body.write(heapq.heappop(packet_heap)[2])

        # put it back to the start
        # so that it can actually be read off of
        body.seek(0)

        return body

    @classmethod
    async def create(cls, main_client,
                     gateway, channel) -> 'VoiceClient':
        """
        Creates a new VoiceClient from a channel and a gateway instance.

        :param main_client: The main :class:`.Client` to use.
        :param gateway: The gateway instance to use.
        :param channel: The :class:`~.Channel` to connect to.
        """
        vs_ws = await VoiceGateway.from_gateway(gw=gateway, channel_id=channel.id,
                                                guild_id=channel.guild.id)
        obb = cls(main_client, channel=channel)
        obb.vs_ws = vs_ws
        obb.main_task = await curio.spawn(obb.poll())
        return obb
