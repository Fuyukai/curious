"""
Decorators to annotate function objects.
"""
from typing import List

from curious.commands.utils import get_description


def command(*,
            name: str = None, description: str = None,
            aliases: List[str] = None, **kwargs):
    """
    Marks a function as a command. This annotates the command with some attributes that allow it
    to be invoked as a command.

    This decorator can be invoked like this:
    .. code-block:: python3

        @command()
        async def ping(self, ctx):
            await ctx.channel.send("Ping!")

    :param name: The name of the command. If this is not specified, it will use the name of the \
        function object.
    :param description: The description of the command. If this is not specified, it will use the \
        first line of the docstring.
    :param aliases: A list of aliases for this command.
    :param kwargs: Anything to annotate the command with.
    """

    # wrapper function that actually marks the object
    def inner(func):
        func.is_cmd = True
        func.cmd_name = name or func.__name__
        func.cmd_description = description or get_description(func)
        func.cmd_aliases = aliases or []
        func.cmd_subcommand = False
        func.cmd_subcommands = []
        func.cmd_parent = None
        func.cmd_conditions = getattr(func, "cmd_conditions", [])

        # annotate command object with any extra
        for ann_name, annotation in kwargs.items():
            ann_name = "cmd_" + name
            setattr(func, ann_name, annotation)

        func.subcommand = _subcommand(func)
        return func

    return inner


def condition(cbl):
    """
    Adds a condition to a command.

    This will add the callable to ``cmd_conditions`` on the function.
    """
    def inner(func):
        if not hasattr(func, "cmd_conditions"):
            func.cmd_conditions = []

        func.cmd_conditions.append(cbl)
        return func

    return inner


def _subcommand(parent):
    """
    Decorator factory set on a command to produce subcommands.
    """
    def inner(**kwargs):
        # MULTIPLE LAYERS
        def inner_2(func):
            cmd = command(**kwargs)(func)
            cmd.cmd_subcommand = True
            cmd.cmd_parent = parent
            parent.cmd_subcommands.append(cmd)
            return cmd

        return inner_2

    return inner

