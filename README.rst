Curious
=======

``curious`` is a Python 3.6+ library to interact with the
`Discord <https://discordapp.com>`_ API.

Installation
------------

Curious is available on PyPI under ``discord-curious``:

.. code-block:: bash

    $ pip install -U discord-curious

Or for the latest development version:

.. code-block:: bash

    $ pip install -U git+https://github.com/Fuyukai/curious.git#egg=curious

Basic Example
-------------

.. code-block:: python3

    from curious import BotType, Client, Message

    cl = Client("token", bot_type=BotType.BOT | BotType.NO_DMS)


    @cl.event("ready")
    async def ready(ctx):
        print("Ready on shard", ctx.shard_id)


    @cl.event("message_create")
    async def handle_message(ctx, message: Message):
        print(f"{message.author.user.name} said '{message.content}'")

    cl.run(shards=1)

Documentation
-------------

See the documentation at https://curious.readthedocs.io/en/latest/.
