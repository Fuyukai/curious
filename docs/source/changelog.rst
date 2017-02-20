Changelog
=========

This document displays the differences between each release of curious.

0.2.0
-----

 - Add user account logging in support.

 - Add ``_friends`` and ``_blocked`` to :class:`State` to represent the friends and blocked users a client has.

 - Add ``friends`` and ``blocked`` properties to :class:`BotUser` which can be used to access the State's attributes.

 - Add a new type called :class:`RelationshipUser` which represents either a friend or a blocked user.

 - Rearrange channel and guild handling in ``READY`` parsing.

 - Fix ``author`` inside private DMs being wrong sometimes.

 - Allow group DMs to work properly.

 - User cache has been redesigned:

    - Users are now cached indefinitely in ``state._users``.

    - Users are referred to by property on :class:`Member` rather than by storing them.
      This should reduce some memory usage as duplicate members will no longer store multiple instances of a user.

    - Users are only decached on a guild member remove.

 - :meth:`State.make_user` now takes a `user_klass` param which allows customization of the user class created when
   caching a user.

 - Users are now updated in ``PRESENCE_UPDATE`` rather than ``GUILD_MEMBER_UPDATE``.

 - ``GUILD_SYNC`` is now supported for user bots.

 - Creating :class:`HTTPClient` with ``bot=False`` will send a user authorization header rather than a bot
   authorization header.

 - Add :meth:`HTTPClient.get_user_profile` to get a user's profile.

 - Add :meth:`HTTPClient.get_app_info` to get the application information for a specific app.
   This method will attempt to download the bot information alongside the app - failing this, it will only request
   the basic app info scope.

 - Remove :meth:`HTTPClient.get_application_info`; call ``get_app_info`` with ``None`` to get the current app's info.

 - Add :meth:`HTTPClient.authorize_bot` to authorize a bot into a guild.

 - Move :class:`AppInfo` into its own module.

 - Add ``bot`` attribute to `AppInfo` which returns the bot user associated with this app.

 - Add :meth:`AppInfo.add_to_guild` which authorizes a bot into a guild.
   Only user accounts can call this.

 - Add :meth:`Client.get_application` to get an :class:`AppInfo` object referring to an application.

 - Add :meth:`HTTPClient.send_friend_request`, :meth:`HTTPClient.remove_relationship`, :meth:`HTTPClient.block_user`
   for editing relationships with users.

 - Add :meth:`User.send_friend_request`, :meth:`User.block`, :meth:`RelationshipUser.remove_friend` and
   :meth:`RelationshipUser.unblock` to manage relationships between users.

 - :class:`BotUser` cannot send friend requests to itself or block itself.

 - Add :meth:`User.get_profile` to get a user's profile.

 - :meth:`Embed.set_image` now validates that the link is a HTTP[S] link.

0.1.4
-----

 - Add :class:`Widget` for support of widgets.

 - Add widget support inside the HTTPClient.

 - Fix events inside cogs.

 - Add new error code mapping to :class:`HTTPException`. This provides clearer display as to what went wrong when
   performing a HTTP method.
