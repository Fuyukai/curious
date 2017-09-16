"""
Defines commands-specific exceptions.
"""


class CommandsError(Exception):
    pass


class ConditionsFailedError(CommandsError):
    """
    Raised when conditions fail for a command.
    """
    def __init__(self, ctx, check):
        self.ctx = ctx
        self.conditions = check

    def __repr__(self):
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

    def __repr__(self):
        return f"Missing required argument `{self.arg}` in `{self.ctx.command_name}`."

    __str__ = __repr__


class CommandInvokeError(Exception):
    """
    Raised when a command has an error during invokation.
    """
    def __init__(self, ctx):
        self.ctx = ctx

    def __repr__(self):
        return f"Command {self.ctx.command_name} failed to invoke with error `{self.__cause__}`."

    __str__ = __repr__


class ConversionFailedError(Exception):
    """
    Raised when conversion fails.
    """
    def __init__(self, ctx, arg: str, to_type: type):
        self.ctx = ctx
        self.arg = arg
        self.to_type = to_type

    def __repr__(self):
        return f"Cannot convert `{self.arg}` to type `{self.to_type.__name__}`."

    __str__ = __repr__
