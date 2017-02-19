"""
Exceptions raised from within the library.
"""
import enum

from curious.http.curio_http import Response


class CuriousError(Exception):
    """
    The base class for all curious exceptions.
    """


# HTTP based exceptions.
class ErrorCode(enum.IntEnum):
    UNKNOWN_ACCOUNT = 10001
    UNKNOWN_APPLICATION = 10002
    UNKNOWN_CHANNEL = 10003
    UNKNOWN_GUILD = 10004
    UNKNOWN_INTEGRATION = 10005
    UNKNOWN_INVITE = 10006
    UNKNOWN_MEMBER = 10007
    UNKNOWN_MESSAGE = 10008
    UNKNOWN_OVERWRITE = 1009
    UNKNOWN_PROVIDER = 10010
    UNKNOWN_ROLE = 10011
    UNKNOWN_TOKEN = 10012
    UNKNOWN_USER = 10013
    UNKNOWN_EMOJI = 10014

    NO_BOTS = 20001
    ONLY_BOTS = 20002

    MAX_GUILDS = 30001  # technically user only
    MAX_FRIENDS = 30002
    MAX_PINS = 30003
    MAX_ROLES = 30005
    MAX_REACTIONS = 30010

    UNAUTHORIZED = 40001
    MISSING_ACCESS = 50001
    INVALID_ACCOUNT = 50002
    NO_DMS = 50003
    EMBED_DISABLED = 50004
    CANNOT_EDIT = 50005
    CANNOT_SEND_EMPTY_MESSAGE = 50006
    CANNOT_SEND_TO_USER = 50007
    CANNOT_SEND_TO_VC = 50008
    VERIFICATION_TOO_HIGH = 50009

    OAUTH2_NO_BOT = 50010
    OAUTH2_LIMIT = 50011
    INVALID_OAUTH_STATE = 50012
    MISSING_PERMISSIONS = 50013
    INVALID_AUTH_TOKEN = 50014

    NOTE_TOO_LONG = 50015
    INVALID_MESSAGE_COUNT = 50016
    CANNOT_PIN = 50019
    TOO_OLD_TO_BULK_DELETE = 50019

    REACTION_BLOCKED = 90001

    UNKNOWN = 0


class HTTPException(CuriousError):
    """
    Raised when a HTTP request fails with a 400 <= e < 600 error code.
    """

    def __init__(self, response: Response, error: dict):
        self.response = response

        #: The error code for this response.
        self.error_code = ErrorCode(error.get("code", 0))
        self.error_message = error.get("message")

        self.error = error

    def __str__(self):
        if self.error_code == ErrorCode.UNKNOWN:
            return repr(self.error)

        return "{}: {}".format(self.error_code, self.error_code.name, self.error_message)

    __repr__ = __str__


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
