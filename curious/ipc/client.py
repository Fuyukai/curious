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
The client for an IPC connection.

.. currentmodule:: curious.ipc.client
"""
import os
import platform
import uuid
from typing import Coroutine

import curio
from curio.io import Socket

from curious.dataclasses.presence import RichPresence
from curious.ipc.packet import IPCOpcode, IPCPacket


def get_ipc_url(slot: int = 0) -> str:
    """
    Gets the IPC URL for Discord.
    """
    if platform.system() == "Linux":
        return f"/run/user/{os.getuid()}/discord-ipc-{slot}"
    elif platform.platform() == "Windows":
        return fr"\\?\pipe\discord-ipc-{slot}"


def get_nonce() -> str:
    """
    Gets a random nonce.
    """
    return str(uuid.uuid4())


class IPCError(Exception):
    """
    Represents an error with the IPC protocol.
    """
    pass


class IPCClient(object):
    """
    Represents an IPC (interprocess communication) client. This connects to the Discord client on
    the IPC socket.

    To use, create a new instance with your app's client ID:

    .. code-block:: python3

        ipc = IPCClient(323578534763298816)

    Make sure to open the client before doing anything with it:

    .. code-block:: python3

        await ipc.open()

    """
    VERSION = 1

    def __init__(self, client_id: int, *, slot: int = 0):
        """
        :param client_id: The client ID to authenticate with.
        """
        self.client_id = client_id

        self._ready = False
        self._sock = None  # type: Socket
        self._ipc_slot = slot

    async def open(self):
        """
        Opens this IPC socket.
        """
        path = get_ipc_url(self._ipc_slot)

        self._sock = await curio.open_unix_connection(path)
        await self._write_handshake()
        next_pack = await self.read_packet()

        if next_pack.opcode == IPCOpcode.CLOSE:
            raise IPCError(next_pack.data)

        if next_pack.event != "READY":
            await self._sock.close()
            raise RuntimeError("Didn't receive a READY event.")
        else:
            self._ready = True

        return self

    # Writer methods
    async def _write_packet(self, packet: IPCPacket):
        """
        Writes an IPC packet.

        :param packet: The :class:`.IPCPacket` to write.
        """
        data = packet.serialize()
        await self._sock.sendall(data)

    def _write_json(self, opcode: IPCOpcode, data: dict) -> Coroutine[None, None, None]:
        """
        Writes JSON to the IPC socket.
        """
        return self._write_packet(IPCPacket(opcode, data))

    def _write_handshake(self):
        """
        Writes an IPC handshake.
        """
        data = {
            "v": IPCClient.VERSION,
            "client_id": str(self.client_id)
        }

        return self._write_json(IPCOpcode.HANDSHAKE, data)

    def _write_rich_presence(self, presence: RichPresence):
        """
        Writes a rich presence packet.
        """
        data = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": presence._rich_fields
            },
            "nonce": get_nonce()
        }
        return self._write_json(IPCOpcode.FRAME, data)

    # Reader methods
    def read_packet(self) -> Coroutine[None, None, IPCPacket]:
        """
        Reads a packet from the connection.
        """
        return IPCPacket.read_packet(self._sock)

    # Convenience methods
    async def send_rich_presence(self, presence: RichPresence):
        """
        Sends a Rich Presence packet to the Discord IPC.

        :param presence: The :class:`.RichPresence` to use.
        """
        if not self._ready:
            raise RuntimeError("Not ready")

        await self._write_rich_presence(presence)
        response = await self.read_packet()

        if response.event == "ERROR":
            raise IPCError(response.data["message"])
