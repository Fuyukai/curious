.. _events:

Event reference
===============

Event names mostly correspond with the event names that are returned from a
dispatch by Discord.

For more information about handling events, see :ref:`better_event_handling`.

State events
------------

.. py:function:: connect(ctx: EventContext)
    :async:

    Called as soon as ``READY`` is received on the gateway. This can be used
    to change status immediately after authentication, for example.

.. py:function:: ready(ctx: EventContext)
    :async:

    Called when a shard has finished streaming guilds and chunked all large
    guilds successfully. This is different to Discord's READY event, which
    fires as soon as the connection has opened.

.. py:function:: shards_ready(ctx: EventContext)
    :async:

    Called when all the shards for a client are ready.

.. py:function:: resumed(ctx: EventContext)
    :async:

    Called when a bot has resumed the connection.

.. py:function:: guild_available(ctx: EventContext, guild: Guild)
    :async:

    Called when a previously unavailable guild becomes available. This is
    **not** called when Unavailable Guilds during streaming become available.
    For that, use :func:`.guild_streamed`.

.. py:function:: guild_join(ctx: EventContext, guild: Guild)
    :async:

    Called when the bot joins a new guild. This is **not** called when
    guilds are streaming. For that, use :func:`.guild_streamed`.

.. py:function:: guild_streamed(ctx: EventContext, guild: Guild)
    :async:

    Called when a guild is streamed during login.

.. py:function:: guild_chunk(ctx: EventContext, guild: Guild, member_count: int)
    :async:

    Called when a guild receives a Guild Member Chunk.

.. py:function:: guild_sync(ctx: EventContext, guild: Guild, member_count: int, \
    presence_count: int)
    :async:

    Called when a guild receives a Guild Sync.

    .. note::

        This is a **user-account only** event.

.. py:function:: guild_unavailable(ctx: EventContext, guild: Guild)
    :async:

    Called when a guild goes unavailable.

.. py:function:: guild_leave(ctx: EventContext, guild: Guild)
    :async:

    Called when the bot leaves a guild.

.. py:function:: guild_update(ctx: EventContext, old_guild: Guild, \
    new_guild: Guild)
    :async:

    Called when a guild updates. This could be from the name changing, icon
    changing, etc.

.. py:function:: guild_emojis_update(ctx: EventContext, old_guild: Guild, \
    new_guild: Guild)
    :async:

    Called when the emojis update in a guild.

.. py:function:: user_settings_update(ctx: EventContext, \
    old_settings: UserSettings, new_settings: UserSettings)
    :async:

    Called when a user's settings update.

    .. note::

        This is a **user-account only** event.


.. py:function:: friend_update(ctx: EventContext, friend: RelationshipUser)
    :async:

    Called when a friend updates (name, presence).

    .. note::

        This is a **user-account only** event.

.. py:function:: relationship_add(ctx: EventContext, user: RelationshipUser)
    :async:

    Called when a relationship is added.

.. py:function:: relationship_remove(ctx: EventContext, user: \
    RelationshipUser)
    :async:

    Called when a relationship is removed.

.. py:function:: guild_member_update(ctx: EventContext, old_member: Member, \
    new_member: Member)
    :async:

    Called when a guild member updates. This could be from typing, roles/nick
    updating, or game changing.

.. py:function:: user_typing(ctx: EventContext, channel: Channel, user: \
    User)
    :async:

    Called when a user is typing (in a private or group DM).

.. py:function:: member_typing(ctx: EventContext, channel: Channel, \
    user: User)
    :async:

    Called when a member is typing (in a guild).

.. py:function:: message_create(ctx: EventContext, message: Message)
    :async:

    Called when a message is created.

.. py:function:: message_update_uncached(ctx: EventContext, messsage: Message)
    :async:

    Called when a message is updated. This will ignore the cache.

.. py:function:: message_edit(ctx: EventContext, old_message: Message, \
    new_message: Message)
    :async:

    Called when a message's content is edited.

    .. warning::

        This event will only be called if a message that the bot has
        previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:function:: message_update(ctx: EventContext, old_message: Message, \
    new_message: Message)
    :async:

    Called when a message is updated (a new embed is added, content is edited,
    etc).

    This will fire on newly added embeds; if you don't want this use
    ``message_edit`` instead.

    .. warning::

        This event will only be called if a message that the bot has
        previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:function:: message_delete_uncached(ctx: EventContext, message_id: int)
    :async:

    Called when a message is deleted. This will ignore the cache.

.. py:function:: message_delete(ctx: EventContext, message: Message)
    :async:

    Called when a message is deleted.

    .. warning::

        This event will only be called if a message that the bot has
        previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:function:: message_delete_bulk_uncached(ctx: EventContext, messages: List[int])
    :async:

    Called when messages are bulk deleted. This will ignore the cache.

.. py:function:: message_delete_bulk(ctx: EventContext, \
    messages: List[Message])
    :async:

    Called when messages are bulk deleted.

    .. warning::

        This event will only be called if any messages that the bot has
        previously seen is in the message cache.
        Otherwise, the bot will silently eat the event.

.. py:function:: message_reaction_add(ctx: EventContext, \
    message: Message, author: Union[Member, User], reaction)
    :async:

    Called when a message is reacted to.

.. py:function:: message_reaction_remove(ctx: EventContext, \
    message, author, reaction)
    :async:

    Called when a reaction is removed from a message.

.. py:function:: message_ack(ctx: EventContext, channel: Channel, \
    message: Message)
    :async:

    Called when a message is ACK'd.

    .. note::

        This is a **user-account only** event.

.. py:function:: guild_member_add(ctx: EventContext, member: Member
    :async:)

    Called when a member is added to a guild.

.. py:function:: guild_member_remove(ctx: EventContext, member: Member)
    :async:

    Called when a member is removed from a guild.

.. py:function:: user_ban(ctx: EventContext, user: User)
    :async:

    Called when a **user** is banned from a guild.

.. py:function:: guild_member_ban(ctx: EventContext, member: Member)
    :async:

    Called when a **member** is banned from a guild.

.. py:function:: user_unban(ctx: EventContext, user: User):
    :async:

    Called when a user is unbanned.

    .. note::

        There is no guild_member_unban event as members cannot be unbanned.

.. py:function:: channel_create(ctx: EventContext, channel: Channel)
    :async:

    Called when a channel is created.

.. py:function:: channel_update(ctx: EventContext, old_channel: Channel, \
    new_channel: Channel)
    :async:

    Called when a channel is updated.

.. py:function:: channel_delete(ctx: EventContext, channel: Channel)
    :async:

    Called when a channel is deleted.

.. py:function:: group_user_add(ctx: EventContext, channel: Channel, \
    user: User)
    :async:

    Called when a user is added to a group.

.. py:function:: group_user_remove(ctx: EventContext, channel: Channel, \
    user: User)
    :async:

    Called when a user is removed from a group.

.. py:function:: role_create(ctx: EventContext, role: Role)
    :async:

    Called when a role is created.

.. py:function:: role_update(ctx: EventContext, old_role: Role, \
    new_role: Role)
    :async:

    Called when a role is updated.

.. py:function:: role_delete(ctx: EventContext, role: Role)
    :async:

    Called when a role is deleted.

.. py:function:: voice_state_update(ctx: EventContext, member, \
    old_voice_state, new_voice_state)
    :async:

    Called when a member's voice state updates.


Gateway Events
--------------

These events are low-level events; they deal with raw data received from the
websocket connection.

.. py:function:: gateway_message_received(ctx: EventContext, data)
    :async:

    Called when a message is received on the websocket.

    .. warning::
        The data is the **RAW DATA** passed from the websocket. It could be
        compressed data; it is undecoded.

        This event is often not useful; see :func:`gateway_event_received` or
        :func:`gateway_dispatch_received` for better functions.

.. py:function:: gateway_event_received(ctx: EventContext, data: dict)
    :async:

    Called when an event is received on the websocket, after decompressing
    and decoding.

.. py:function:: gateway_hello(ctx: EventContext, trace: List[str])
    :async:

    Called when HELLO is received.

.. py:function:: gateway_heartbeat(ctx: EventContext, stats)
    :async:

    Called when a heartbeat is sent.

.. py:function:: gateway_heartbeat_ack(ctx: EventContext)
    :async:

    Called when Discord ACKs a heartbeat we've sent.

.. py:function:: gateway_heartbeat_received(ctx: EventContext)
    :async:

    Called when Discord asks us to send a heartbeat.

.. py:function:: gateway_invalidate_session(ctx: EventContext, resume: bool)
    :async:

    Called when Discord invalidates our session.

.. py:function:: gateway_reconnect_received(ctx: EventContext)
    :async:

    Called when Discord asks us to send a reconnect.

.. py:function:: gateway_dispatch_received(ctx: EventContext, \
    dispatch: dict)
    :async:

    Called when an event is dispatched.
