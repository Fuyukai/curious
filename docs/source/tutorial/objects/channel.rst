.. _tutorial_channel:

The Channel Object
==================

The :class:`.Channel` object is one of the key objects when it comes to dealing with Discord.
Each message has an associated channel, and your bot will probably want to be dealing with
messages a lot, including replying or sending messages out of the blue.

Message Handling
----------------

The most important part of a channel is message handling - that is, being able to send messages,
upload files, and view logs for the channel.
Curious provides a neat wrapper over the message handling part of the channel, which provides
some utility methods, the :class:`.ChannelMessageWrapper`.

To send a message to a channel, you can use :meth:`.Channel.messages.send`, like so:

.. code-block:: python3

    # basic message
    await channel.messages.send("hello, world!")

    # sending an embed
    em = Embed()
    em.description = "Hello, world!"
    await channel.messages.send(embed=em)

File uploads are also supported, using :meth:`.Channel.messages.upload`:

.. code-block:: python3

    # upload from a path
    await channel.messages.upload(content="Check it out",
                                  fp=Path("/home/laura/Downloads/cool.jpg"))

    # or directly from bytes
    await channel.messages.upload(fp=some_buffer.read(1024), filename="random_data.bin")

You can also receive a log of messages sent in the channel by iterating over the message wrapper:

.. code-block:: python3

    # use the magic async iterator
    async for message in channel.messages:
        print(message.content)

    # fine-tune history
    async for message in channel.messages.history(limit=500):
        print(message.content)

    # alternatively, get a single message
    message = await channel.messages.get(some_message_id)

Deleting is easy and powerful using :meth:`.Channel.messages.bulk_delete` or
:meth:`.Channel.messages.purge`:

.. code-block:: python3

    # delete messages from yourself in the last 100 messages
    count_1 = await channel.messages.purge(limit=100, author=channel.guild.me)

    # alternatively, delete messages beginning with "and"
    count_2 = await channel.messages.purge(limit=100, predicate=lambda m: m.startswith("and"))

