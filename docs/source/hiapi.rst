
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

.. autoclass:: curious.event.EventContext
    :members:


Event reference
~~~~~~~~~~~~~~~

Event names mostly correspond with the event names that are returned from a dispatch by Discord.

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

.. py:cofunction:: member_update(ctx: EventContext, old_member: Member, new_member: Member)

    Called when a guild member updates. This could be from typing, roles/nick updating, or game changing.

.. py:cofunction:: guild_update(ctx: EventContext, old_guild: Guild, new_guild: Guild)

    Called when a guild updates. This could be from the name changing, icon changing, etc.

.. py:cofunction:: guild_unavailable(ctx: EventContext, guild: Guild)

    Called when a guild goes unavailable.

.. py:cofunction:: guild_leave(ctx: EventContext, guild: Guild)

    Called when the bot leaves a guild.

.. py:cofunction:: guild_emojis_update(ctx: EventContext, old_guild: Guild, new_guild: Guild)

    Called when the emojis update in a guild.

.. py:cofunction:: message_create(ctx: EventContext, message: Message)

    Called when a message is created.

.. py:cofunction:: message_update(ctx: EventContext, old_message: Message, new_message: Message)

    Called when a message is edited.

    .. warning::

        This event will only be called if a message that the bot has previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:cofunction:: message_delete(ctx: EventContext, message: Message)

    Called when a message is deleted.

    .. warning::

        This event will only be called if a message that the bot has previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:cofunction:: message_delete_bulk(ctx: EventContext, messages: List[Message])

    Called when messages are bulk deleted.

    .. warning::

        This event will only be called if any messages that the bot has previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:cofunction:: message_reaction_add(ctx: EventContext, message: Message, author: Union[Member, User], reaction)

    Called when a message is reacted to.

.. py:cofunction:: message_reaction_remove(ctx: EventContext, message, author, reaction)

    Called when a reaction is removed from a message.

.. py:cofunction:: member_join(ctx: EventContext, member: Member)

    Called when a member is added to a guild.

.. py:cofunction:: member_leave(ctx: EventContext, member: Member)

    Called when a member is removed from a guild.

.. py:cofunction:: user_ban(ctx: EventContext, user: User)

    Called when a **user** is banned from a guild.

.. py:cofunction:: member_ban(ctx: EventContext, member: Member)

    Called when a **member** is banned from a guild.

.. py:cofunction:: channel_create(ctx: EventContext, channel: Channel)

    Called when a channel is created.

.. py:cofunction:: channel_update(ctx: EventContext, old_channel: Channel, new_channel: Channel)

    Called when a channel is updated.

.. py:cofunction:: channel_delete(ctx: EventContext, channel: Channel)

    Called when a channel is deleted.

.. py:cofunction:: role_create(ctx: EventContext, role: Role)

    Called when a role is created.

.. py:cofunction:: role_update(ctx: EventContext, old_role: Role, new_role: Role)

    Called when a role is updated.

.. py:cofunction:: role_delete(ctx: EventContext, role: Role)

    Called when a role is deleted.

.. py:cofunction:: voice_state_update(ctx: EventContext, member, old_voice_state, new_voice_state)

    Called when a member's voice state updates.


Client
------

.. autoclass:: curious.core.client.Client
    :members:


Voice
-----

.. autoclass:: curious.voice.voice_client.VoiceClient
    :members: send_voice_packet, send_opus_data, play_file


Dataclasses
-----------

These classes, with the exception of :class:`Game`, :class:`PermissionsOverwrite` or :class:`Embed` should not created
by your code. Instead, you should use the built-in methods to access the correct instances of these classes.

IDObject & Dataclass
~~~~~~~~~~~~~~~~~~~~

All dataclasses described below have an ``id`` property that they inherit from these classes.

.. autoclass:: curious.dataclasses.bases.IDObject
    :members:

.. autoclass:: curious.dataclasses.bases.Dataclass

AppInfo
~~~~~~~

.. autoclass:: curious.dataclasses.appinfo.AppInfo
    :members:

User
~~~~

.. autoclass:: curious.dataclasses.user.User
    :members:
    :inherited-members:

Member
~~~~~~

All members have access to the underlying :class:`User` on the ``user`` property. This is unlike some other libraries
where Member is a direct subclass of User.

.. autoclass:: curious.dataclasses.member.Member
    :members:
    :inherited-members:
    :private-members:

Webhook
~~~~~~~

.. autoclass:: curious.dataclasses.webhook.Webhook
    :members:
    :inherited-members:
    :private-members:

Guild
~~~~~

.. autoclass:: curious.dataclasses.guild.Guild
    :members:
    :inherited-members:
    :private-members:

Channel
~~~~~~~

.. autoclass:: curious.dataclasses.channel.Channel
    :members:
    :inherited-members:
    :private-members:

Role
~~~~

.. autoclass:: curious.dataclasses.role.Role
    :members:
    :inherited-members:

Message
~~~~~~~

.. autoclass:: curious.dataclasses.message.Message
    :members:
    :inherited-members:
    :private-members:

Game
~~~~

.. autoclass:: curious.dataclasses.status.Game
    :members:
    :inherited-members:
    :private-members:

Reaction
~~~~~~~~

.. autoclass:: curious.dataclasses.reaction.Reaction
    :members:
    :inherited-members:
    :private-members:

Emoji
~~~~~

.. autoclass:: curious.dataclasses.emoji.Emoji
    :members:
    :inherited-members:
    :private-members:

Embed
~~~~~

.. autoclass:: curious.dataclasses.embed.Embed
    :members:
    :inherited-members:
    :private-members:

Invite
~~~~~~

.. autoclass:: curious.dataclasses.invite.InviteGuild
    :members:
    :inherited-members:
    :private-members:

.. autoclass:: curious.dataclasses.invite.InviteChannel
    :members:
    :inherited-members:
    :private-members:

.. autoclass:: curious.dataclasses.invite.Invite
    :members:
    :inherited-members:
    :private-members:

.. autoclass:: curious.dataclasses.invite.InviteMetadata
    :members:
    :inherited-members:
    :private-members:

Permissions
~~~~~~~~~~~

.. autoclass:: curious.dataclasses.permissions.Permissions
    :members:
    :inherited-members:
    :private-members:

.. autoclass:: curious.dataclasses.permissions.Overwrite
    :members:
    :inherited-members:
    :private-members:


Widget
~~~~~~

.. autoclass:: curious.dataclasses.widget.Widget
    :members:
    :inherited-members:

.. autoclass:: curious.dataclasses.widget.WidgetGuild
    :members:
    :inherited-members:

.. autoclass:: curious.dataclasses.widget.WidgetChannel
    :members:
    :inherited-members:

.. autoclass:: curious.dataclasses.widget.WidgetMember
    :members:
    :inherited-members:
