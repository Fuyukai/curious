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
Represents a Discord IPC packet.

.. currentmodule:: curious.client.packet
"""
import enum
import json
import struct
import uuid
from io import BytesIO

from curio.io import Socket


class IPCOpcode(enum.IntEnum):
    """
    Represents an IPC opcode.
    """
    HANDSHAKE = 0
    FRAME = 1
    CLOSE = 2
    PING = 3
    PONG = 4


class IPCPacket(object):
    """
    Represents an IPC packet.
    """
    def __init__(self, opcode: IPCOpcode, data: dict):
        """
        :param opcode: The :class:`.IPCOpcode` for this packet.
        :param data: A dict of data enclosed in this packet.
        """
        self.opcode = opcode
        self._json_data = data

    @staticmethod
    def _pack_json(data: dict) -> str:
        """
        Packs JSON in a compact representation.
        :param data: The data to pack.
        """
        return json.dumps(data, indent=None, separators=(',', ':'))

    # properties
    @property
    def event(self) -> str:
        """
        Gets the event for this packet. Received packets only.
        """
        return self._json_data["evt"]

    @property
    def cmd(self) -> str:
        """
        Gets the command for this packet.
        """
        return self._json_data["cmd"]

    @property
    def nonce(self) -> uuid.UUID:
        """
        Gets the nonce for this packet.
        """
        return uuid.UUID(self._json_data["nonce"])

    @property
    def data(self) -> str:
        """
        Gets the inner data for this packet.
        """
        return self._json_data["data"]

    def serialize(self) -> bytes:
        """
        Serializes this packet into a series of bytes.
        """
        buf = BytesIO()
        # Add opcode - little endian (why not network order?)
        buf.write(self.opcode.to_bytes(4, byteorder="little"))
        data = self._pack_json(self._json_data)
        # Add data length - little endian (why not network order?)
        buf.write(len(data).to_bytes(4, byteorder="little"))
        # Add data - string, obviously
        buf.write(data.encode("utf-8"))
        return buf.getvalue()

    @classmethod
    def deserialize(cls, data: bytes):
        """
        Deserializes a full packet.

        This method is not usually what you want.
        """
        opcode, length = struct.unpack("<ii", data[:8])
        raw_data = data[8:].decode("utf-8")

        if len(raw_data) != length:
            raise ValueError("Got invalid length.")

        return IPCPacket(IPCOpcode(opcode), json.loads(raw_data))

    @classmethod
    async def read_packet(cls, sock: Socket) -> 'IPCPacket':
        """
        Reads a packet off of the socket, and deserializes it.
        """
        data = await sock.recv(8)

        if len(data) != 8:
            raise ValueError("Got bad IPC read")

        # unpack header so we can get the length
        opcode, length = struct.unpack("<ii", data)

        # read body based on header
        body = await sock.recv(length)
        body_data = json.loads(body.decode("utf-8"))
        return IPCPacket(IPCOpcode(opcode), body_data)
