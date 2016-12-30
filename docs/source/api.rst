.. py:currentmodule:: curious

API Reference
=============

This document outlines the usage of the curious API.


Client
------

.. autoclass:: curious.client.Client
    :members:


Dataclasses
-----------

These classes, with the exception of :class:`Game` or :class:`PermissionsOverwrite`, should not created by your code.
 Instead, you should use the built-in methods to access the correct instances of these classes.

.. autoclass:: curious.dataclasses.user.User
    :members:

.. autoclass:: curious.dataclasses.member.Member
    :members:

.. autoclass:: curious.dataclasses.guild.Guild
    :members:

.. autoclass:: curious.dataclasses.channel.Channel
    :members:

.. autoclass:: curious.dataclasses.role.Role
    :members:

.. autoclass:: curious.dataclasses.message.Message
    :members:

.. autoclass:: curious.dataclasses.permissions.Permissions
    :members:

