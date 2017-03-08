"""
Commands helpers.

.. currentmodule:: curious.commands

.. autosummary::
    :toctree: commands
    
    cmd
    context
    exc
    plugin
"""
import functools
import typing

from curious.commands.cmd import Command


def command(*args, klass: type = Command, **kwargs):
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


def group(*args, klass: type = Command, **kwargs):
    """
    A decorator to mark a function as a group command.

    This takes the same parameters as the normal ``command`` decorator. The returned function will have a `command`
    attribute which can be used to create a new command, and a `group` attribute which can be used to make subgroups.
    """

    def __inner(func):
        # nested hell!
        # this is similar to the `command` decorator defined above, except it appends to `subcommands` on the
        # function with the factory.

        # the function objects left in the command object do NOT get registered as normal commands, as we leave a
        # mark that tells the scanner not to add them.
        def _command_attr(*args, klass: type = Command, **kwargs):
            def _i_command_attr(_func):
                f = command(*args, klass=klass, **kwargs)(_func)
                func.subcommands.append(f.factory)
                # mark - do not add!
                f._subcommand = True
                return f

            return _i_command_attr

        def _group_attr(*args, klass: type = Command, **kwargs):
            def _i_group_attr(_func):
                f = group(*args, klass=klass, **kwargs)(_func)
                func.subcommands.append(f.factory)
                f._subcommand = True
                return f

            return _i_group_attr

        factory = functools.partial(klass, func, *args, group=True, **kwargs)
        func.factory = factory
        func.subcommands = []
        func.command = _command_attr
        func.group = _group_attr

        return func

    return __inner
