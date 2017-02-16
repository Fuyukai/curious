"""
A lower-level State that doesn't do any special object handling.
"""
import inspect

import typing

from curious.core.gateway import Gateway
from curious.core.state import State


class PureDispatchState(State):
    """
    A lower-level State that doesn't do any special object handling.
    This state allows you to pass JSON data straight to the event handlers registered on the Client instance.

    To use this instead of the base high-level state, you have to pass this as a class to the Client instance:

    .. code:: python

        my_client = Client(state_klass=PureDispatchState)
    """

    def _fake_handle(self, event_name: str):
        """
        Returns a function that can pretend to handle the event, when all it does is dispatch the raw data.

        :param event_name: The event name we're handling.
        """

        async def _inner(gw: Gateway, event_data: dict):
            await self.client.dispatch(event_name, event_data, gateway=gw)

        return _inner

    def __getattribute__(self, item):
        # Intercept any `handle_` things.
        if not item.startswith("handle_"):
            return super().__getattribute__(item)

        return self._fake_handle(item.split("handle_")[1])


class CallbackState(PureDispatchState):
    """
    An even lower-level State that invokes a single callback when an event is received.

    This callback must have the signature of (gw: Gateway, event: str, data: dict) -> None.

    This state can be passed directly into a Gateway instance to be used as the state instance.
    """
    def __init__(self, callback: typing.Callable[[Gateway, str, dict], None]):
        super().__init__(None)

        self.callback = callback

    def _fake_handle(self, event_name: str):
        async def _inner(gw: Gateway, event_data: dict):
            result = self.callback(gw, event_name, event_data)
            if inspect.isawaitable(result):
                result = await result

        return _inner
