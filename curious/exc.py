"""
Exceptions raised from within the library.
"""


class CuriousError(Exception):
    """
    The base class for all curious exceptions.
    """


class PermissionsError(CuriousError):
    """
    Raised when you do not have sufficient permission to perform an action.

    :ivar permission_required: The string of the permission required to perform this action.
    """

    def __init__(self, permission_required: str):
        self.permission_required = permission_required

    def __str__(self):
        return "You require the permission {} to perform this action".format(self.permission_required)

    __repr__ = __str__


class HierachyError(CuriousError):
    """
    Raised when you can't do something due to the hierachy.
    """
