Changelog
=========

This document displays the differences between each release of curious.

0.3.0
-----

 - :meth:`.Client.start` will now automatically reboot shards that return.

 - Add :meth:`.HTTPClient.get_authorized_apps` to get the authorized apps for this account.

 - Add :meth:`.HTTPClient.revoke_authorized_app` to revoke an application's authorization.

 - Add :meth:`.BotUser.get_authorized_apps` as the high-level equivalent.

 - Add :attr:`~.Message.channel_id` and :attr:`~.Message.author_id` to access the raw IDs from Discord, even if the
   message author or channel is not cached.

 - Unprivatize :meth:`~.State.find_channel` and add :meth:`~.Client.find_channel` to use this method.

0.2.1
-----

 - Sync/chunk guilds when a ``GUILD_CREATE`` is received during the main bot lifecycle.

 - Decache users automatically when a ``GUILD_DELETE`` is received.

 - Fix the default role not being accounted for in permissions.

 - Fix ``GUILD_ROLE_DELETE`` handling.

 - Fix async threads hanging the bot on shutdown.

 - Add the ability to set ``afk`` in a presence change, to allow self-bots to not eat notifications.

 - Userbots will now ask for member chunks and then sync guilds once all chunks are received.

 - Make :attr:`.Guild.large` a property rather than an attribute.
   Discord doesn't always send this properly, so fallback to ``member_count >= 250``.

0.2.0
-----

 - Add user account logging in support.

 - Add :attr:`~.State._friends` and :attr:`~.State._blocked` to :class:`.State` to represent the friends and blocked
   users a client has.

 - Add :attr:`~.BotUser.friends` and :attr:`~.BotUser.blocked` properties to :class:`.BotUser` which can be used to
   access the State's attributes.

 - Add a new type called :class:`.RelationshipUser` which represents either a friend or a blocked user.

 - Rearrange channel and guild handling in ``READY`` parsing.

 - Fix :attr:`~.Channel.author` inside private DMs being wrong sometimes.

 - Allow group DMs to work properly.

 - User cache has been redesigned:

    - Users are now cached indefinitely in :attr:`~.State._users`.

    - Users are referred to by property on :class:`.Member` rather than by storing them.
      This should reduce some memory usage as duplicate members will no longer store multiple instances of a user.

    - Users are only decached on a guild member remove.

 - :meth:`.State.make_user` now takes a ``user_klass`` param which allows customization of the user class created when
   caching a user.

 - Users are now updated in ``PRESENCE_UPDATE`` rather than ``GUILD_MEMBER_UPDATE``.

 - ``GUILD_SYNC`` is now supported for user bots.

 - Creating :class:`~.HTTPClient` with ``bot=False`` will send a user authorization header rather than a bot
   authorization header.

 - Add :meth:`.HTTPClient.get_user_profile` to get a user's profile.

 - Add :meth:`.HTTPClient.get_app_info` to get the application information for a specific app.
   This method will attempt to download the bot information alongside the app - failing this, it will only request
   the basic app info scope.

 - Remove :meth:`.HTTPClient.get_application_info`; call ``get_app_info`` with ``None`` to get the current app's info.

 - Add :meth:`.HTTPClient.authorize_bot` to authorize a bot into a guild.

 - Move :class:`.AppInfo` into its own module.

 - Make :class:`.AppInfo` more useful than just the current application's info.

 - Add :attr:`~.AppInfo.bot` attribute to :class:`~.AppInfo` which returns the bot user associated with this app.

 - Add :meth:`.AppInfo.add_to_guild` which authorizes a bot into a guild.
   Only user accounts can call this.

 - Add :meth:`.Client.get_application` to get an :class:`AppInfo` object referring to an application.

 - Add :meth:`.HTTPClient.send_friend_request`, :meth:`.HTTPClient.remove_relationship`,
   :meth:`.HTTPClient.block_user` for editing relationships with users.

 - Add :meth:`.User.send_friend_request`, :meth:`.User.block`, :meth:`.RelationshipUser.remove_friend` and
   :meth:`.RelationshipUser.unblock` to manage relationships between users.

 - :class:`.BotUser` cannot send friend requests to itself or block itself.

 - Add :meth:`.User.get_profile` to get a user's profile.

 - :meth:`.Embed.set_image` now validates that the link is a HTTP[S] link.

0.1.4
-----

 - Add :class:`.Widget` for support of widgets.

 - Add widget support inside the HTTPClient.

 - Fix events inside cogs.

 - Add new error code mapping to :class:`.HTTPException`. This provides clearer display as to what went wrong when
   performing a HTTP method.
