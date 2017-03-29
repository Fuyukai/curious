Event reference
~~~~~~~~~~~~~~~

Event names mostly correspond with the event names that are returned from a
dispatch by Discord.


.. py:cofunction:: connect(ctx: EventContext)

    Called as soon as ``READY`` is received on the gateway. This can be used
    to change status immediately after authentication, for example.

.. py:cofunction:: ready(ctx: EventContext)

    Called when a bot has finished streaming guilds and chunked all large
    guilds successfully. This is different to Discord's READY event, which
    fires as soon as the connection has opened.

.. py:cofunction:: guild_available(ctx : EventContext, guild : Guild)

    Called when a previously unavailable guild becomes available. This is
    **not** called when Unavailable Guilds during streaming become available.
    For that, use :func:`.guild_streamed`.

.. py:cofunction:: guild_join(ctx: EventContext, guild: Guild)

    Called when the bot joins a new guild. This is **not** called when
    guilds are streaming. For that, use :func:`.guild_streamed`.

.. py:cofunction:: guild_streamed(ctx: EventContext, guild: Guild)

    Called when a guild is streamed during login.

.. py:cofunction:: guild_chunk(ctx: EventContext, guild: Guild)

    Called when a guild receives a Guild Member Chunk.

.. py:cofunction:: guild_sync(ctx: EventContext, guild: Guild)

    Called when a guild receives a Guild Sync.

    .. note::

        This is a **user-account only** event.

.. py:cofunction:: member_update(ctx: EventContext, old_member: Member, \
    new_member: Member)

    Called when a guild member updates. This could be from typing, roles/nick
    updating, or game changing.

.. py:cofunction:: guild_update(ctx: EventContext, old_guild: Guild, \
    new_guild: Guild)

    Called when a guild updates. This could be from the name changing, icon
    changing, etc.

.. py:cofunction:: guild_unavailable(ctx: EventContext, guild: Guild)

    Called when a guild goes unavailable.

.. py:cofunction:: guild_leave(ctx: EventContext, guild: Guild)

    Called when the bot leaves a guild.

.. py:cofunction:: guild_emojis_update(ctx: EventContext, old_guild: Guild, \
    new_guild: Guild)

    Called when the emojis update in a guild.

.. py:cofunction:: message_create(ctx: EventContext, message: Message)

    Called when a message is created.

.. py:cofunction:: message_update(ctx: EventContext, old_message: Message, \
    new_message: Message)

    Called when a message is edited.

    .. warning::

        This event will only be called if a message that the bot has
        previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:cofunction:: message_delete(ctx: EventContext, message: Message)

    Called when a message is deleted.

    .. warning::

        This event will only be called if a message that the bot has
        previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:cofunction:: message_delete_bulk(ctx: EventContext, \
    messages: List[Message])

    Called when messages are bulk deleted.

    .. warning::

        This event will only be called if any messages that the bot has
        previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:cofunction:: message_reaction_add(ctx: EventContext, \
    message: Message, author: Union[Member, User], reaction)

    Called when a message is reacted to.

.. py:cofunction:: message_reaction_remove(ctx: EventContext, \
    message, author, reaction)

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

.. py:cofunction:: channel_update(ctx: EventContext, old_channel: Channel, \
    new_channel: Channel)

    Called when a channel is updated.

.. py:cofunction:: channel_delete(ctx: EventContext, channel: Channel)

    Called when a channel is deleted.

.. py:cofunction:: role_create(ctx: EventContext, role: Role)

    Called when a role is created.

.. py:cofunction:: role_update(ctx: EventContext, old_role: Role, \
    new_role: Role)

    Called when a role is updated.

.. py:cofunction:: role_delete(ctx: EventContext, role: Role)

    Called when a role is deleted.

.. py:cofunction:: voice_state_update(ctx: EventContext, member, \
    old_voice_state, new_voice_state)

    Called when a member's voice state updates.
