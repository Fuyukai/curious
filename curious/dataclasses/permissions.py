"""
Wrappers for Permission objects.

This class uses some automatic generation to create the objects.

.. currentmodule:: curious.dataclasses.permissions
"""

import typing

from curious.dataclasses import member as dt_member, role as dt_role


# I'm far too lazy to type out each permission bit manually.
# So here's a helper method.
def build_permissions_class(name: str = "Permissions") -> type:
    """
    Builds the permissions class automagically.
    This should ***not*** be used by normal user code - it is designed for internal usage by curious.

    :param name: The name of the class.
    :return: A new type representing the permissions class.
    """
    # Closure methods.
    __doc__ = """
    Represents the permissions a user can have.
    This type is automatically generated based upon a set of constant permission bits.

    Every permission is accessible via a property getter and setter. The raw permissions value is accessible via
    ``bitfield``.
    """

    def __init__(self, value: int = 0):
        """
        Creates a new Permissions object.

        :param value: The bitfield value of the permissions object.
        """
        self.bitfield = value

    def __new__(cls, value):
        if isinstance(value, cls):
            return value

        return super(Permissions, cls).__new__(cls)

    def _get_bit(self, bit: int) -> bool:
        """
        Gets a bit from the internal bitfield of the permissions.
        """

        return bool((self.bitfield >> bit) & 1)

    def _set_bit(self, bit: int, value: bool):
        if value:
            self.bitfield |= (1 << bit)
        else:
            self.bitfield &= ~(1 << bit)

    # Operator overloads.
    def __eq__(self, other):
        return self.bitfield == other.bitfield

    # This is a dict because discord skips some permissions.
    permissions = {
        "create_instant_invite": 0,
        "kick_members": 1,
        "ban_members": 2,
        "administrator": 3,
        "manage_channels": 4,
        "manage_server": 5,
        "add_reactions": 6,
        "read_messages": 10,
        "send_messages": 11,
        "send_tts_messages": 12,
        "manage_messages": 13,
        "embed_links": 14,
        "attach_files": 15,
        "read_message_history": 16,
        "mention_everyone": 17,
        "use_external_emojis": 18,
        "voice_connect": 20,
        "voice_speak": 21,
        "voice_mute_members": 22,
        "voice_deafen_members": 23,
        "voice_move_members": 24,
        "voice_use_voice_activation": 25,
        "change_nickname": 26,
        "manage_nicknames": 27,
        "manage_roles": 28,
        "manage_webhooks": 29,
        "manage_emojis": 30,
        # rest are unused
    }

    # Create a bunch of property objects for each permission.
    def _get_permission_getter(name: str, bit: int):
        def _junk_function(self) -> bool:
            return self._get_bit(bit)

        _junk_function.__name__ = name
        return _junk_function

    def _get_permission_setter(name: str, bit: int):
        def _junk_function(self, value: bool):
            return self._set_bit(bit, value)

        _junk_function.__name__ = name
        return _junk_function

    _doc_base = ":return: If this member has the {} permission (bit {})."

    properties = {
        name: property(fget=_get_permission_getter(name, bit),
                       fset=_get_permission_setter(name, bit),
                       doc=_doc_base.format(name, bit)) for (name, bit) in permissions.items()
        }

    # Create some useful classmethods.
    @classmethod
    def all(cls):
        """
        :return: A new Permissions object with all permissions.
        """
        return cls(9007199254740991)

    @classmethod
    def none(cls):
        """
        :return: A new permissions object with no permissions.
        """
        return cls(0)

    # Create the namespace dict to use in the type declaration.
    namespace = {
        "__init__": __init__,
        "__new__": __new__,
        "_set_bit": _set_bit,
        "_get_bit": _get_bit,
        "__eq__": __eq__,
        "__repr__": lambda self: "<Permissions value={}>".format(self.bitfield),
        "all": all,
        "none": none,
        "__slots__": ("bitfield",),
        **properties
    }
    new_class = type(name, (object,), namespace)
    new_class.__doc__ = __doc__

    return new_class


Permissions = build_permissions_class("Permissions")


class Overwrite(object):
    """
    Represents a permission overwrite.

    This has all properties that the base Permissions object, but it takes into accounts the overwrites for the
    channels. It is always recommended to use this over the server permissions, as it will fall back to the default
    permissions for the role if it can't find specific overwrites.

    The overwrite has a permission marked as ``True`` if the object has a) an overwrite on the channel OR b) the object
    has that permission and no overwrite. The overwrite is marked as ``False`` if the object has a) an overwrite on
    the channel OR b) the object does not have that permission and no overwrite/a deny overwrite.

    You can set an attribute to None to clear the overwrite, True to set an allow overwrite, and False to set a deny
    overwrite.

    :ivar allow: The :class:`Permissions` object that represents the allowed items for this overwrite.
    :ivar deny: The :class:`Permissions` object that represents the denied items for this overwrite.
    :ivar target: The original object that this overwrite is for. This can either be a role or a member.
    """

    __slots__ = "target", "channel", "allow", "deny"

    def __init__(self, allow: typing.Union[int, Permissions], deny: typing.Union[int, Permissions], obb, channel=None):
        self.target = obb

        self.channel = channel

        self.allow = Permissions(value=allow if allow is not None else 0)
        self.deny = Permissions(value=deny if deny is not None else 0)

    def __repr__(self):
        return "<Overwrites for object={} channel={} allow={} deny={}>".format(self.target, self.channel, self.allow,
                                                                               self.deny)

    def __getattr__(self, item):
        """
        Attribute getter helper.

        This will check allow first, the deny, then finally the role permissions.
        """
        if isinstance(self.target, dt_member.Member):
            permissions = self.target.guild_permissions
        elif isinstance(self.target, dt_role.Role):
            permissions = self.target.permissions
        else:
            raise TypeError("Target must be a member or a role")

        if permissions.administrator:
            # short-circuit to always return True if they have administrator
            # this is because those overrides are useless
            # if the user wants to get the override, they can access `allow/deny` directly.
            return True

        if not hasattr(self.allow, item):
            raise AttributeError(item)

        if getattr(self.allow, item, None) is True:
            return True

        if getattr(self.deny, item, None) is True:
            # Return False because it's denied.
            return False

        return getattr(permissions, item, False)

    def __setattr__(self, key, value):
        """
        Attribute setter helper.
        """
        if not hasattr(Permissions, key):
            super().__setattr__(key, value)
            return

        if value is False:
            setattr(self.deny, key, True)
        elif value is True:
            setattr(self.allow, key, True)
        elif value is None:
            setattr(self.allow, key, False)
            setattr(self.deny, key, False)
