.. py:currentmodule:: curious

Low-Level API Reference
=======================

Curious' API is split into two parts:

 - The **high-level** API
 - The **low-level** API

The **high-level** API consists of the client wrappers and the dataclasses. The **low-level API** allows you to
handle this all for yourself, without curious meddling inbetween.


HTTP Handling
-------------

The :class:`HTTPClient` is used to make HTTP requests to Discord's API. It can be used by itself without the usage of
a client.

To create your own HTTPClient, simply construct it with your token:

.. code:: python

    from curious.http.httpclient import HTTPClient

    my_http = HTTPClient("token")

.. autoclass:: curious.http.httpclient.HTTPClient
    :members:

Gateway handling
----------------

The :class:`Gateway` is used to connect to the websocket. The gateway is tied into the state more - the gateway
requires a class passed in as the second argument that has ``handle_*`` methods which can be used to parse incoming
events from the gateway.

Additionally, the gateway needs a constant polling loop to pull new events from the websocket and to handle them.

.. code-block:: python

    class MyState(object):
        ...

    from curious.gateway import Gateway

    async def main():
        my_gateway = await Gateway.from_token("token", MyState(), "wss://gateway.discord.gg/")
        while True:
            await my_gateway.next_event()


.. autoclass:: curious.gateway.Gateway
    :members:

State handling
--------------

The :class:`State` stores state for the current websocket connection.

.. autoclass:: curious.state.State
    :members:

There are also alternative implementations of state that can be used for more low-level purposes.

.. autoclass:: curious.ext.loapi.PureDispatchState
    :members:

.. autoclass:: curious.ext.loapi.CallbackState
    :members:
