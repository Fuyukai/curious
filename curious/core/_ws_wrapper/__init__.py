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