
High-level API Reference
========================

This document outlines the usage of the high-level curious API.

Events
------

Events are the main way of listening to actions that happen on Discord.
Events are registered with the ``@commands.event`` decorator (for plugins) or the ``@bot.event`` decorator (for
bot-level events).

All events take at least one parameter, the :class:`EventContext` that contains the shard ID and the bot instance
used for the event.

Example for event registration:

.. code-block:: python

    @commands.event("message_create")
    async def process_message(ctx: EventContext, message: Message):
        ...

Event names mostly correspond with the event names that are returned from a dispatch by Discord (for a full list of
these events, see `The Discord API docs <https://discordapp.com/developers/docs/topics/gateway#events>`_.) However,
there are some events that do not line up:

.. py:cofunction:: connect(ctx: EventContext)

    Called as soon as ``READY`` is received on the gateway. This can be used to change status immediately after
    authentication.

.. py:cofunction:: ready(ctx: EventContext)

    Called when a bot has finished streaming guilds and chunked all large guilds successfully. This is different to
    Discord's READY event, which fires as soon as the connection has opened.

.. py:cofunction:: guild_available(ctx : EventContext, guild : Guild)

    Called when a previously unavailable guild becomes available. This is **not** called when Unavailable Guilds
    during streaming become available.

.. py:cofunction:: guild_join(ctx: EventContext, guild: Guild)

    Called when the bot joins a new guild. This is **not** called when guilds are streaming.

.. autoclass:: curious.event.EventContext
    :members:


Client
------

.. autoclass:: curious.client.Client
    :members:


Voice
-----

.. autoclass:: curious.voice.voice_client.VoiceClient
    :members: send_voice_packet, send_opus_data, play_file


Dataclasses
-----------

These classes, with the exception of :class:`Game`, :class:`PermissionsOverwrite` or :class:`Embed` should not created
by your code. Instead, you should use the built-in methods to access the correct instances of these classes.

AppInfo
~~~~~~~

.. autoclass:: curious.client.AppInfo
    :members:

User
~~~~

.. autoclass:: curious.dataclasses.user.User
    :members:

Member
~~~~~~

All members have access to the underlying :class:`User` on the ``user`` property. This is unlike some other libraries
where Member is a direct subclass of User.

.. autoclass:: curious.dataclasses.member.Member
    :members:

Webhook
~~~~~~~

.. autoclass:: curious.dataclasses.webhook.Webhook
    :members:

Guild
~~~~~

.. autoclass:: curious.dataclasses.guild.Guild
    :members:

Channel
~~~~~~~

.. autoclass:: curious.dataclasses.channel.Channel
    :members:

Role
~~~~

.. autoclass:: curious.dataclasses.role.Role
    :members:

Message
~~~~~~~

.. autoclass:: curious.dataclasses.message.Message
    :members:

Game
~~~~

.. autoclass:: curious.dataclasses.status.Game
    :members:

Reaction
~~~~~~~~

.. autoclass:: curious.dataclasses.reaction.Reaction
    :members:

Emoji
~~~~~

.. autoclass:: curious.dataclasses.emoji.Emoji
    :members:

Embed
~~~~~

.. autoclass:: curious.dataclasses.embed.Embed
    :members:

Invite
~~~~~~

.. autoclass:: curious.dataclasses.invite.InviteGuild
    :members:

.. autoclass:: curious.dataclasses.invite.InviteChannel
    :members:

.. autoclass:: curious.dataclasses.invite.Invite
    :members:

.. autoclass:: curious.dataclasses.invite.InviteMetadata
    :members:

Permissions
~~~~~~~~~~~

.. autoclass:: curious.dataclasses.permissions.Permissions
    :members:

.. autoclass:: curious.dataclasses.permissions.Overwrite
    :members:
