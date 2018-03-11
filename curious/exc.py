# This file is part of curious.
#
# curious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# curious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with curious.  If not, see <http://www.gnu.org/licenses/>.

"""
Exceptions raised from within the library.

.. currentmodule:: curious.exc
"""
import enum
import warnings

from asks.response_objects import Response


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
    MAX_GUILD_CHANNELS = 30013

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
    INVALID_VANITY_URL = 50020
    TOO_OLD_TO_BULK_DELETE = 50034
    INVALID_FORM_BODY = 50035
    INVALID_INVITE_GUILD = 50036

    REACTION_BLOCKED = 90001

    UNKNOWN = 0


class HTTPException(CuriousError, ConnectionError):
    """
    Raised when a HTTP request fails with a 400 <= e < 600 error code.
    """

    def __init__(self, response: Response, error: dict):
        self.response = response

        error_code = error.get("code", 0)
        try:
            #: The error code for this response.
            self.error_code = ErrorCode(error_code)
        except ValueError:
            warnings.warn("Received unknown error code {}")
            #: The error code for this response.
            self.error_code = ErrorCode.UNKNOWN
        self.error_message = error.get("message")

        self.error = error

    def __str__(self) -> str:
        if self.error_code == ErrorCode.UNKNOWN:
            return repr(self.error)

        return "{} ({}): {}".format(self.error_code, self.error_code.name, self.error_message)

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


class PermissionsError(CuriousError, PermissionError):
    """
    Raised when you do not have sufficient permission to perform an action.

    :ivar permission_required: The string of the permission required to perform this action.
    """

    def __init__(self, permission_required: str):
        self.permission_required = permission_required

    def __str__(self) -> str:
        return "Bot requires the permission {} to perform this action"\
            .format(self.permission_required)

    __repr__ = __str__


class HierarchyError(CuriousError, PermissionError):
    """
    Raised when you can't do something due to the hierarchy.
    """
