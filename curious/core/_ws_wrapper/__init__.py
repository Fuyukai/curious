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
Websocket wrapper classes, using a different backend library.
"""
import abc
from collections import AsyncIterable


class BasicWebsocketWrapper(AsyncIterable):
    """
    The base class for a basic websocket wrapper.
    """
    _done = object()

    def __init__(self, url: str) -> None:
        #: The gateway URL.
        self.url = url

    @abc.abstractclassmethod
    async def open(cls, url: str) -> 'BasicWebsocketWrapper':
        """
        Opens this websocket.
        """

    @abc.abstractmethod
    async def close(self, code: int = 1000, reason: str = "Client closed connection",
                    reconnect: bool = False) -> None:
        """
        Cancels and closes this websocket.

        :param code: The close code for this websocket.
        :param reason: The close reason for this websocket.
        :param reconnect: If the websocket should reconnect after being closed.
        """

    @abc.abstractmethod
    async def send_text(self, text: str) -> None:
        """
        Sends text down the websocket.
        """