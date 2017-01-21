"""
Commands helpers.
"""
import functools

from curious.commands.command import Command


def command(*args, klass: type=Command, **kwargs):
    """
    A decorator to mark a function as a command.
    This will put a `factory` attribute on the function, which can later be called to create the Command instance.

    All arguments are passed to the Command class.

    :param klass: The command class type to wrap the object in.
    """

    def __inner(func):
        factory = functools.partial(klass, func, *args, **kwargs)
        func.factory = factory
        return func

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
