.. py:currentmodule:: curious

High-level API Reference
========================

This document outlines the usage of the high-level curious API.


Client
------

.. autoclass:: curious.client.Client
    :members:


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
