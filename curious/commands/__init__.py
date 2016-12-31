"""
Commands helpers.
"""
from curious.commands.command import Command


def command(*args, **kwargs) -> 'Command':
    """
    A decorator to mark a function as a command.
    This can then be later used to register

    All arguments are passed to the Command class.
    """

    def __inner(func):
        return Command(func, *args, **kwargs)

    return __inner


def event(func):
    """
    Marks a function as an event.

    :param func: Either the function, or the name to give to the event.
    """
    if isinstance(func, str):
        def __innr(f):
            f.event = func
            return f

        return __innr
    else:
        func.event = func.__name__[3:]
        return func
