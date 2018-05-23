Changelog
=========

This document displays the differences between each release of curious.

0.7.8 (Released 2018-05-23)
---------------------------

 - Fix :meth:`.HTTPClient.leave_guild`.

 - Fix a crash on ``MEMBER_UPDATE`` packets.

 - Make mentions in DMs return correctly (and also, not crash).

 - Fix new :class:`.VoiceState` objects not having a client object.

 - Add the ability to move members into a different voice channel.

 - Add ``zlib-stream`` as the compression method for the gateway.

0.7.7 (Released 2018-04-04)
---------------------------

 - Fix trying to convert a default.

 - Add a :class:`typing.Union` converter.

0.7.6 (Released 2018-04-03)
---------------------------

 - Fix conversion with missing arguments on positional arguments.

 - Unwrap :class:`.Nickname` objects in the nickname setter.

 - Pass the value, not the :class:`.Nickname` object, to the nickname setter.

0.7.5 (Released 2018-04-01)
---------------------------

 - Don't crash when trying to fill in guild fields without a cached guild.

0.7.4 (Released 2018-03-27)
---------------------------

 - Fix for negative ratelimit sleep times.

 - Don't crash when copying a nickname incorrectly.

0.7.3 (Released 2018-03-27)
---------------------------

 - Don't immediately disconnect on boot.

0.7.2 (Released 2018-03-27)
---------------------------

 - Changed :class:`.Nickname` to be a proper object, and not a string wrapper.

 - Fix ``Member.roles._sorted_roles`` to sort in reverse order.

 - Attempt at adding better reconnect logic.

0.7.1 (Released 2018-03-12)
---------------------------

 - Fixed :meth:`.Channel.permissions` (thanks PyCharm)

0.7.0 (Released 2018-03-11)
---------------------------

 - Add get-by-name to :class:`.GuildChannelWrapper`, and :class:`.GuildRoleWrapper`.

 - Add :attr:`.Invite.features`.

 - Add :class:`.GameType` for game types.

 - Make :attr:`.Invite.inviter` a property that returns a :class:`.Member` if one can be found.

 - Remove :meth:`.Client.boot_shard` amongst others, and create :meth:`.Client.handle_shard` to
   do all gateway-related handling functions.

 - Add :attr:`.Channel.overwrites` for a key-value mapping of overwrites.

 - Add :class:`.Nickname`, and make :attr:`.Member.nickname` an instance of :class:`.Nickname`.

 - Add :meth:`.EventManager.wait_for_manager`.

 - Rename ``MEMBER_`` events to ``GUILD_MEMBER_`` events.

 - Add :class:`._MemberRoleContainer`, and make :attr:`.Member.roles` an instance of this.

 - Add :attr:`.Message.emojis`.

 - Add :class:`.ChannelMessagesWrapper`, and move everything to point to it.

 - Rewrite the gateway code significantly.

    - Use Lomond in a thread instead of our own wrapper.

    - Make opening a gateway a context manager.

    - Use proper dataclasses for state.

 - Add :class:`.AvatarUrl`.

 - Add :class:`.GuildBan`, and make :meth:`.Guild.get_bans` return a list of those.

 - Move :attr:`.Guild._splash_hash` and :attr:`.Guild._icon_hash` to public attributes.

 - Add a ``permissions.pyi`` file for static introspection of the permissions class.

 - Add a :class:`.GuildBanContainer`.

 - Enable :mod:`trio` support.

 - Add :func:`.autoplugin` which automatically assigns commands inside a plugin.

 - Add :meth:`.Plugin.spawn` for easy background task spawning.

 - Add :attr:`.Channel.children` to get the children of a channel.

 - Deprivatize :meth:`.State.find_message`.

 - Lookup messages in the cache to avoid a roundtrip when doing :meth:`.ChannelMessagesWrapper.get`.


0.6.0 (Released 2017-11-05)
---------------------------

 - Bring voice code inline with the standard of the rest of the code.

    - Change the voice gateway to use an async thread, rather than a regular thread.

    - Document and make public :meth:`.VoiceClient.get_packet_header`,
      :meth:`.VoiceClient.get_voice_packet` and :meth:`.VoiceClient.get_ip_discovery_packet`.

 - Make :class:`.AppInfo` a subclass of :class:`.Dataclass`.

 - Only sleep on shard creation until the last shard.

 - Move :meth:`.Channel.is_private` to :meth:`.Channel.private`.

 - Move :meth:`.IDObject.timestamp` to :meth:`.IDObject.snowflake_timestamp`.

 - Make some things use ID references rather than object references, and deprivatize the ID
   attributes on these objects.

 - Add support for channel categories in the API and the gateway.

 - Reorganize commands code significantly:

    - Move all of the commands code out of :class:`.Client`.

    - Add new :class:`.CommandsManager`.

    - Overhaul :class:`.Context` to do more, such as the actual processing.

    - Remove :class:`.Command` in favour of annotated functions.

 - Reorganize events code significantly:

    - Move all the events code out of :class:`.Client`.

    - Add new :class:`.EventManager`.

    - Add event hooks, which are called with every event the bot receives.

    - Overhaul :meth:`.EventManager.wait_for` so that it uses :class:`curio.Promise` rather than
      terrible events.

    - Change temporary listeners to raising ListenerExit instead of returning a truthy/falsey value.

 - Reboot shards properly when they disconnect, using a while True loop inside the TaskGroup.

 - Add :attr:`.State.guilds_ordered`.

 - Add a 5 second timeout to each request made.

 - Add :meth:`.Message.get_invites` and :attr:`.Message.invites` to get invites that are inside a
   message object.

 - Retry on h11 errors.

 - Use :mod:`asyncwebsockets` instead of :mod:`cuiows`.

 - :class:`.ReactionPaginator` can now have an optional title that is added as the content for
   the message sent.

0.5.1 (Released 2017-08-19)
---------------------------

 - Switch to the ``asks`` HTTP library over the bundled HTTP library.

 - Add :class:`.MessageType`.

 - Add :attr:`.ChannelType.CATEGORY`.

 - Separate out HTTP URLs into a :class:`.Endpoints` class.

 - Properly wait on shards in the start handler.

0.5.0 (Released 2017-07-31)
---------------------------

 .. warning::

    This is the last version of curious that supports Python 3.5.

 - Add :meth:`.HTTPClient.get_audit_logs`.

 - Add gateway event dispatching.

 - Add :meth:`.HTTPClient.get_vanity_url` and
   :meth:`.HTTPClient.edit_vanity_url`.

 - Add :meth:`.Guild.get_vanity_invite` and :meth:`.Guild.set_vanity_invite`.

 - :meth:`.Guild.get_invites` will now return the vanity invite, if applicable.

 - Rearrange guild objects somewhat:

    - Turn :attr:`.Guild.channels` into a :class:`.GuildChannelWrapper`.

    - Turn :attr:`.Guild.roles` into a :class:`.GuildRoleWrapper`.

    - Move :meth:`.Guild.create_channel` to :meth:`.GuildChannelWrapper.create`.

    - Move :meth:`.Guild.edit_channel` to :meth:`.Channel.edit`.

    - Move :meth:`.Guild.delete_channel` to :meth:`.Channel.delete`.

    - Move :meth:`.Guild.create_role` to :meth:`.GuildRoleWrapper.create`.

    - Move :meth:`.Guild.edit_role` to :meth:`.Role.edit`.

    - Move :meth:`.Guild.delete_role` to :meth:`.Role.delete`.

 - Add a ``message_mentioned`` event.

 - Add :attr:`.User.static_avatar_url`.

 - :attr:`.Guild.large` now obeys a custom ``large_threshold``.

 - Add counts to ``guild_chunk`` and ``guild_sync`` events.

 - Fix editing profile via :meth:`.User.edit`.

 - Add :meth:`.HTTPClient.get_user_applications` and :meth:`.HTTPClient.get_application`.

 - Don't include ``@everyone`` when calculating role colours.


0.4.0 (Released 2017-04-27)
---------------------------

 - :class:`.VoiceState` now uses a property reference to the User object.

 - Add :meth:`.HTTPClient.get_mentions`.

 - Add :attr:`.BotUser.authorized_apps` which returns an async iterator
   that can be used to get the authorized apps for this bot.

 - Add :meth:`.BotUser.get_recent_mentions` and
   :meth:`.Guild.get_recent_mentions` to allow easy iteration of recent
   mentions.

 - Change statuses to new :class:`~.Presence`, which are stored on Member
   and RelationshipUser instances.

 - :attr:`.Guild._large` is now set by GUILD_SYNC handling for userbots.

 - Optimize :meth:`.State.make_message` slightly, by checking the cache
   before editing it.

 - :meth:`._prepare_request` automatically stringifies all items in the
   query string before sending it.

 - Add search support:

    - :meth:`.HTTPClient.search_channel` and
      :meth:`.HTTPClient.search_guild` are the raw HTTP methods for
      searching.

    - :class:`.SearchQuery`, :class:`.SearchResults` and
      :class:`.MessageGroup` are the high level wrappers for searching.

 - Add :meth:`.AsyncIteratorWrapper.next` and
   :meth:`.AsyncIteratorWrapper.all`.

 - Change :class:`~.Guild` objects on dataclasses to mostly look up via
   property or weak reference rather than having a strong reference.

 - Change commands:

    - A callable that takes ``(bot, message)`` and returns (a) prefix(es)
      to match can now be provided for ``command_prefix``.

    - Functions are unwrapped for the `.factory` attr if possible.

 - Add the ability to listen to multiple events with one function.

 - Add :class:`~.MFALevel`, :class:`~.VerificationLevel`,
   :class:`~.NotificationLevel`, :class:`~.ContentFilterLevel`, and update
   the relevant attributes on :class:`~.Guild`.

 - Add HTTP downloading methods to :class:`~.Client`.

 - Add :attr:`.Channel.nsfw`.

0.3.0 (Released 2017-03-10)
---------------------------

 - :meth:`.Client.start` will now automatically reboot shards that return.

 - Add :meth:`.HTTPClient.get_authorized_apps` to get the authorized apps for
   this account.

 - Add :meth:`.HTTPClient.revoke_authorized_app` to revoke an application's
   authorization.

 - Add :meth:`.BotUser.get_authorized_apps` as the high-level equivalent.

 - Add :attr:`.Message.channel_id` and :attr:`.Message.author_id` to access
   the raw IDs from Discord, even if the message author or channel is not
   cached.

 - Unprivatize :meth:`.State.find_channel` and add
   :meth:`.Client.find_channel` to use this method.

 - Unprivatize :meth:`.State.is_ready`.

 - Change sharding slightly:

    - :meth:`.Client.boot_shard` will boot one shard and add its gateway
      to the internal list.
      This will allow finer control over shard booting.

    - :meth:`.Client.start` will now use ``boot_shard`` to load a shard, so
      overriding it in a subclass can customize shard creation.

 - The client will now wait for the gateway to be ready before firing any
   events.

 - Add :class:`.BotType` to more finely control how bots are defined.

 - Add :attr:`.EventContext.event_name`, :attr:`.EventContext.handlers`.

 - Add :attr:`.Client.events_handled` and :attr:`.Gateway._dispatches_handled`
   to show how many events have been handled during the lifetime of the bot.

 - Add :class:`.GuildStore` which tracks the order of guilds for user bots,
   and can be used to return the guilds in that order.

 - Change :class:`.Channel` for group DMs slightly:

    - New attributes have been added: :attr:`.Channel.owner`,
      :attr:`.Channel.owner_id`, :attr:`.Channel._icon_hash`,
      :attr:`.Channel.icon_url`.

    - :attr:`.Channel._recipients` has been added to replace ``recipients``
      as the backing store, and is now a dict.

    - Correspondingly, :attr:`.Channel.recipients` is a mapping proxy for
      ``Channel._recipients``, and can be used to access the recipients of
      the channel.

 - Add :meth:`.HTTPClient.update_user_settings` to update the settings of a
   user.

 - Add :class:`.UserSettings` to represent the settings of a user.

 - Add event handler for ``USER_SETTINGS_UPDATE``.

0.2.1 (Released 2017-02-23)
---------------------------

 - Sync/chunk guilds when a ``GUILD_CREATE`` is received during the main bot
   lifecycle.

 - Decache users automatically when a ``GUILD_DELETE`` is received.

 - Fix the default role not being accounted for in permissions.

 - Fix ``GUILD_ROLE_DELETE`` handling.

 - Fix async threads hanging the bot on shutdown.

 - Add the ability to set ``afk`` in a presence change, to allow self-bots to
   not eat notifications.

 - Userbots will now ask for member chunks and then sync guilds once all
   chunks are received.

 - Make :attr:`.Guild.large` a property rather than an attribute.
   Discord doesn't always send this properly, so fallback to
   ``member_count >= 250``.

0.2.0 (Released 2017-02-20)
---------------------------

 - Add user account logging in support.

 - Add :attr:`~.State._friends` and :attr:`~.State._blocked` to
   :class:`.State` to represent the friends and blocked users a client has.

 - Add :attr:`~.BotUser.friends` and :attr:`~.BotUser.blocked` properties to
   :class:`.BotUser` which can be used to access the State's attributes.

 - Add a new type called :class:`.RelationshipUser` which represents either a
   friend or a blocked user.

 - Rearrange channel and guild handling in ``READY`` parsing.

 - Fix :attr:`~.Channel.author` inside private DMs being wrong sometimes.

 - Allow group DMs to work properly.

 - User cache has been redesigned:

    - Users are now cached indefinitely in :attr:`~.State._users`.

    - Users are referred to by property on :class:`.Member` rather than by
      storing them.
      This should reduce some memory usage as duplicate members will no longer
      store multiple instances of a user.

    - Users are only decached on a guild member remove.

 - :meth:`.State.make_user` now takes a ``user_klass`` param which allows
   customization of the user class created when caching a user.

 - Users are now updated in ``PRESENCE_UPDATE`` rather than
   ``GUILD_MEMBER_UPDATE``.

 - ``GUILD_SYNC`` is now supported for user bots.

 - Creating :class:`~.HTTPClient` with ``bot=False`` will send a user
   authorization header rather than a bot authorization header.

 - Add :meth:`.HTTPClient.get_user_profile` to get a user's profile.

 - Add :meth:`.HTTPClient.get_app_info` to get the application information
   for a specific app.
   This method will attempt to download the bot information alongside the
   app - failing this, it will only request the basic app info scope.

 - Remove :meth:`.HTTPClient.get_application_info`; call ``get_app_info``
   with ``None`` to get the current app's info.

 - Add :meth:`.HTTPClient.authorize_bot` to authorize a bot into a guild.

 - Move :class:`.AppInfo` into its own module.

 - Make :class:`.AppInfo` more useful than just the current application's
   info.

 - Add :attr:`~.AppInfo.bot` attribute to :class:`~.AppInfo` which returns
   the bot user associated with this app.

 - Add :meth:`.AppInfo.add_to_guild` which authorizes a bot into a guild.
   Only user accounts can call this.

 - Add :meth:`.Client.get_application` to get an :class:`AppInfo` object
   referring to an application.

 - Add :meth:`.HTTPClient.send_friend_request`,
   :meth:`.HTTPClient.remove_relationship`,
   :meth:`.HTTPClient.block_user` for editing relationships with users.

 - Add :meth:`.User.send_friend_request`, :meth:`.User.block`,
   :meth:`.RelationshipUser.remove_friend` and
   :meth:`.RelationshipUser.unblock` to manage relationships between users.

 - :class:`.BotUser` cannot send friend requests to itself or block itself.

 - Add :meth:`.User.get_profile` to get a user's profile.

 - :meth:`.Embed.set_image` now validates that the link is a HTTP[S] link.

0.1.4
-----

 - Add :class:`.Widget` for support of widgets.

 - Add widget support inside the HTTPClient.

 - Fix events inside plugins.

 - Add new error code mapping to :class:`.HTTPException`.
   This provides clearer display as to what went wrong when performing a
   HTTP method.
