# I'm far too lazy to type out each permission bit manually.
# So here's a helper method.


def build_permissions_class(name: str="Permissions"):
    # Closure methods.
    def __init__(self, value: int = 0):
        """
        Creates a new Permissions object.

        :param value: The bitfield value of the permissions object.
        """
        self.bitfield = value

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
    # Create the namespace dict to use in the type declaration.
    namespace = {
        "__init__": __init__,
        "_set_bit": _set_bit,
        "_get_bit": _get_bit,
        "__eq__": __eq__,
        **properties
    }
    new_class = type(name, (object,), namespace)

    return new_class

Permissions = build_permissions_class("Permissions")
