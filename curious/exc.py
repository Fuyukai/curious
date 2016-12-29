"""
Exceptions raised from within the library.
"""
from curious.http.curio_http import Response


class CuriousError(Exception):
    """
    The base class for all curious exceptions.
    """


class HTTPException(CuriousError):
    """
    Raised when a HTTP request fails with a 400 <= e < 600 error code.
    """

    def __init__(self, response: Response, error: dict):
        self.response = response
        self.error = error

    def __repr__(self):
        return repr(self.error)

    def __str__(self):
        return str(self.error)


class Unauthorized(HTTPException):
    """
    Raised when your bot token is invalid.
    """


class Forbidden(HTTPException):
    """
    Raised when you don't have permission for something.
    """


class NotFound(HTTPException):
    """
    Raised when something could not be found.
    """


class PermissionsError(CuriousError):
    """
    Raised when you do not have sufficient permission to perform an action.

    :ivar permission_required: The string of the permission required to perform this action.
    """

    def __init__(self, permission_required: str):
        self.permission_required = permission_required

    def __str__(self):
        return "Bot requires the permission {} to perform this action".format(self.permission_required)

    __repr__ = __str__


class HierachyError(CuriousError):
    """
    Raised when you can't do something due to the hierachy.
    """
