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
import collections
import datetime
import heapq
import logging
import socket
import struct
import time
from io import BytesIO
from typing import List, Tuple, Union

import curio
from curio.io import Socket
from curio.socket import getaddrinfo
from nacl.secret import SecretBox
from opuslib import Decoder, Encoder

from curious.dataclasses import member as dt_member, user as dt_user
from curious.dataclasses.bases import Dataclass
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


class VoiceMessage:
    """
    A container for a voice message.
    """

    def __init__(self):
        #: A BytesIO containing PCM frames at 48k bitrate.
        self.pcm = BytesIO()

        #: The timestamp, in UTC, for when this message started.
        self.start_time: datetime.datetime = None

        #: The timestamp, in UTC, for when this message ended.
        self.stop_time: datetime.datetime = None

        #: The user ID of the person speaking for this message.
        self.user_id: int = None


class VoiceReceiver:
    """
    A class that allows arbitrary starting and stopping of recording voice.
    """

    def __init__(self, cl: 'VoiceClient'):
        self.client = cl

        # buffers for the packet heap
        self._buffers = collections.defaultdict(lambda: [])

        self._started: bool = False
        self._task: curio.Task = None

    async def _listen(self):
        """
        Listens to voice data, storing it in a buffer.
        """
        # wrap the socket so we dont spawn a billion threads
        sock = Socket(self.client._sock)

        # dict of dicts
        # {buffer: [], last_packet: [], start_time: datetime, ssrc: int}
        _temporary_buffers = {}

        def _copy_buffer(tmp: dict) -> None:
            """
            Copies a temporary receive buffer into proper buffers.
            """
            # copy out the data into a VoiceMessage
            ssrc = tmp["ssrc"]

            msg = VoiceMessage()
            for frame in sorted(tmp["buffer"], key=lambda i: i[1]):
                msg.pcm.write(frame[2])

            msg.pcm.seek(0)
            msg.start_time = tmp["start_time"]
            msg.stop_time = datetime.datetime.utcnow()
            msg.user_id = self.client.vs_ws.ssrc_mapping[ssrc]
            self._buffers[ssrc].append(msg)

        def _check_buffers() -> None:
            _mark = []
            # pass 1, copy out any finished messages
            for subdict in _temporary_buffers.values():
                # stopped talking for 1000ms
                if (time.monotonic() - subdict["last_packet"]) >= 1:
                    _copy_buffer(subdict)
                    # mark it for deletion next time around
                    _mark.append(ssrc)

            # pass 2, delete any old temporary buffers
            for marked in _mark:
                _temporary_buffers.pop(marked)

        while self._started:
            _check_buffers()

            try:
                # timeout after half a second so we can re-check our buffers
                data = await curio.timeout_after(0.5, sock.recv(8192))
            except curio.TaskTimeout:
                # we timed out, continue to check the
                continue
            except curio.TaskCancelled:
                # copy out all data into buffers
                for buf in _temporary_buffers.values():
                    _copy_buffer(buf)
                return

            ssrc, sequence, timestamp, data = self.client.unpack_packet(data)
            if ssrc not in _temporary_buffers:
                d = {
                    "buffer": [],
                    "last_packet": time.monotonic(),
                    "start_time": datetime.datetime.utcnow(),
                    "ssrc": ssrc
                }
                _temporary_buffers[ssrc] = d
            else:
                d = _temporary_buffers[ssrc]

            # push the new voice packet onto the temporary buffer
            item = (sequence, timestamp, data)
            heapq.heappush(d["buffer"], item)
            # set the new time value so we know when to remove old packets
            d["last_packet"] = time.monotonic()

    async def start(self):
        """
        Starts receiving voice.
        """
        if self._started:
            return

        self._started = True
        # empty out our buffers
        self._buffers.clear()
        self._task = await curio.spawn(self._listen)

    async def stop(self):
        """
        Stops receiving voice.
        """
        if not self._started:
            return

        self._stop_time = datetime.datetime.utcnow()
        await self._task.cancel(blocking=False)

    def get_data(self, user: 'Union[int, dt_user.User, dt_member.Member, None]' = None) \
            -> 'List[VoiceMessage]':
        """
        Gets the data for a user in the buffers.

        .. note::

            If the user is not in voice, or has not sent anything, this will return an empty
            BytesIO.

        :param user: The :class:`.User`, :class:`.Member` or int ssrc to get the data of.
        :return: A :class:`BytesIO` containing the PCM data for the user.
        """
        if isinstance(user, Dataclass):
            user_id = user.id
            ssrc = next(filter(lambda i: i[1] == user_id, self.client.vs_ws.ssrc_mapping.items()),
                        None)

            # return empty
            if ssrc is None:
                return []
            ssrc = ssrc[0]
        elif isinstance(user, int):
            ssrc = user
        else:
            raise ValueError("Must pass a User/Member or ssrc")

        msgs = self._buffers.get(ssrc, [])
        return msgs


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

        pcm_frames = self.decoder.decode(decrypted, 960)

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

    def get_receiver(self) -> 'VoiceReceiver':
        """
        Get a voice receiver that can be used to receive voice.
        """
        if not self.open:
            raise RuntimeError("Voice client must be open")

        if self._sock is None:
            raise RuntimeError("Voice client must be connected to UDP")

        return VoiceReceiver(self)

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
