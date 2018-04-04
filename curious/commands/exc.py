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
Defines commands-specific exceptions.

.. currentmodule:: curious.commands.exc
"""
import time
from math import ceil
from typing import Tuple

from curious.exc import CuriousError


class CommandsError(CuriousError):
    pass


class ConditionsFailedError(CommandsError):
    """
    Raised when conditions fail for a command.
    """
    def __init__(self, ctx, check):
        self.ctx = ctx
        self.conditions = check

    def __repr__(self) -> str:
        if isinstance(self.conditions, list):
            return f"The conditions for `{self.ctx.command_name}` failed."

        return f"The condition `{self.conditions.__name__}` for `{self.ctx.command_name}` failed." \

    __str__ = __repr__


class MissingArgumentError(CommandsError):
    """
    Raised when a command is missing an argument.
    """
    def __init__(self, ctx, arg):
        self.ctx = ctx
        self.arg = arg

    def __repr__(self) -> str:
        return f"Missing required argument `{self.arg}` in `{self.ctx.command_name}`."

    __str__ = __repr__


class CommandInvokeError(CommandsError):
    """
    Raised when a command has an error during invokation.
    """
    def __init__(self, ctx):
        self.ctx = ctx

    def __repr__(self) -> str:
        return f"Command {self.ctx.command_name} failed to invoke with error `{self.__cause__}`."

    __str__ = __repr__


class ConversionFailedError(CommandsError):
    """
    Raised when conversion fails.
    """
    def __init__(self, ctx, arg: str, to_type: type, message: str = "Unknown error"):
        self.ctx = ctx
        self.arg = arg
        self.to_type = to_type
        self.message = message

    def __repr__(self) -> str:
        try:
            name = getattr(self.to_type, "__name__")
        except AttributeError:
            name = repr(self.to_type)

        return f"Cannot convert `{self.arg}` to type `{name}`: {self.message}."

    __str__ = __repr__


class CommandRateLimited(CommandsError):
    """
    Raised when a command is ratelimited.
    """
    def __init__(self, context, func, limit, bucket: Tuple[int, float]):
        self.ctx = context
        self.func = func
        self.limit = limit
        self.bucket = bucket

    def __repr__(self) -> str:
        left = int(ceil(self.bucket[1] - time.monotonic()))
        return f"The command {self.ctx.command_name} is currently rate limited for " \
               f"{left} second(s)."

    __str__ = __repr__