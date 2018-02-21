.. _firstbot:

Writing your First Bot
======================

This tutorial assumes several things:

 - You have installed curious successfully

 - You have created a bot account successfully

This tutorial will go over writing a bot that echos all messages to your
console when they are received by the bot.

The Project
-----------

As your bot is incredibly simple, it probably will not need more than a
single file currently. Your basic bot skeleton layout should look something
like:

.. code-block:: bash

    $ ls --tree

    └── bot.py

The ``bot.py`` file will contain all of the code for the bot.

Writing the Bot
---------------

Open up ``bot.py`` and add the essential imports:

.. code-block:: python3

    import multio
    from curious.core.client import Client

This will import the :class:`.Client`, which is used to communicate with
Discord, and :mod:`multio` which is used to pick your backend.

Before anything else, you need to choose an async library to run your bot with:

.. code-block:: python3

    multio.init('curio')  # lean mean killing machine
    multio.init('trio')  # lean mean maiming machine

Next, you want to define your new bot object, passing your bot token to it:

.. code-block:: python3

    botto = Client("MjYwOTUwODE2NTM2NTI2ODQ5.Cz2mGQ.SKl78a6NT6SBpwYQrIDnR1olPqo")

This object will be used to receive events from Discord, such as the messages.

Event Handling
--------------

To process events from Discord, you need to **subscribe to an event**. This
will call a function automatically every single time an event is received
by the websocket connection to process the event.

To receive new messages automatically, we have to subscribe to the
``message_create`` event, using :meth:`.Client.event`.

.. code-block:: python3

    @botto.event("message_create")
    async def my_handler(ctx, message):
        pass

The handler function is decorated with the event decorator, which takes the
event name to process as an argument.

All event handlers take one argument, the :class:`.EventContext` which
contains a small amount of context about the event. Right now, this is not
needed for our purposes.

The second argument to the ``message_create`` event is a :class:`.Message`
object, which represents a message sent by Discord. We are interested in
:attr:`.Message.content`, to print to the console.

Modify the body of the function so that it prints to the console the
message content:

.. code-block:: python3

    print("Content:", message.content)


Running the Bot
---------------

The final stage to this basic tutorial is to **run the bot**.

The simplest method is to call :meth:`.Client.run`, like so:

.. code-block:: python3

    botto.run()

When you type in a server that you and the bot account share, you will then
see your messages pop up in the log for the bot.
