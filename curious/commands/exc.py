"""
Defines commands-specific exceptions.
"""


class CommandsError(Exception):
    pass


class CheckFailureError(Exception):
    def __init__(self, ctx, check):
        self.ctx = ctx
        self.check = check

    def __repr__(self):
        if isinstance(self.check, list):
            return "The checks for `{.name}` failed.".format(self.ctx)
        return "The check `{.__name__}` for `{.name}` failed.".format(self.check, self.ctx)

    __str__ = __repr__


class MissingArgumentError(Exception):
    def __init__(self, ctx, arg):
        self.ctx = ctx
        self.arg = arg

    def __repr__(self):
        return "Missing required argument `{}` in `{.name}`.".format(self.arg, self.ctx)

    __str__ = __repr__


class CommandInvokeError(Exception):
    def __init__(self, ctx):
        self.ctx = ctx

    def __repr__(self):
        return "Command {.name} failed to invoke with error `{}`.".format(self.ctx, self.__cause__)

    __str__ = __repr__


class ConversionFailedError(Exception):
    def __init__(self, ctx, arg: str, to_type: type):
        self.ctx = ctx
        self.arg = arg
        self.to_type = to_type

    def __repr__(self):
        return "Cannot convert `{}` to type `{.__name__}`.".format(self.arg, self.to_type)

    __str__ = __repr__
