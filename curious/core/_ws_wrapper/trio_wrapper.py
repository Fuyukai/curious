"""
A trio websocket wrapper.
"""
import functools
import threading
from collections import AsyncIterator

import trio
from lomond import WebSocket
from lomond.events import Event
from lomond.persist import persist

from curious import USER_AGENT
from curious.core._ws_wrapper import BasicWebsocketWrapper


class TrioWebsocketWrapper(BasicWebsocketWrapper):
    """
    Implements a websocket handler for Trio.
    """

    def __init__(self, url: str, nursery):
        """
        :param url: The gateway URL.
        :param nursery: The nursery to use.
        """
        super().__init__(url)

        self.nursery = nursery

        self._portal = trio.BlockingTrioPortal()
        self._queue = trio.Queue(capacity=5)
        self._cancelled = threading.Event()
        self._ws = None  # type: WebSocket

    def websocket_task(self) -> None:
        """
        Runs the websocket task.
        """
        ws = WebSocket(self.url, agent=USER_AGENT)
        self._ws = ws
        # generate poll events every 0.5 seconds to see if we can cancel
        websocket = persist(ws, ping_rate=0, poll=1, exit_event=self._cancelled)
        for event in websocket:
            self._portal.run(self._queue.put, event)

        # signal the end of the queue
        self._portal.run(self._queue.put, self._done)

    @classmethod
    async def open(cls, url: str, nursery) -> 'BasicWebsocketWrapper':
        """
        Opens a new websocket connection.

        :param url: The URL to use.
        :param nursery: The nursery to use.
        """
        obb = cls(url, nursery)
        partial = functools.partial(trio.run_sync_in_worker_thread)
        nursery.start_soon(partial, obb.websocket_task)
        return obb

    async def close(self, code: int = 1000, reason: str = "Client closed connection",
                    reconnect: bool = False) -> None:
        """
        Closes the websocket.

        :param code: The close code to use.
        :param reason: The close reason to use.
        """
        if not reconnect:
            self._cancelled.set()

        await trio.run_sync_in_worker_thread(functools.partial(self._ws.close, code=code,
                                                               reason=reason))

    async def send_text(self, text: str) -> None:
        """
        Sends text down the websocket.

        :param text: The text to send.
        """
        await trio.run_sync_in_worker_thread(functools.partial(self._ws.send_text, text))

    async def __aiter__(self) -> 'AsyncIterator[Event]':
        async for item in self._queue:
            if item == self._done:
                return

            yield item
