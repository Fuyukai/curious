"""
Decorators to annotate function objects.
"""
from typing import List

from curious.commands.utils import get_description


def command(func=None, *,
            name: str = None, description: str = None,
            aliases: List[str] = None):
    """
    Marks a function as a command. This annotates the command with some attributes that allow it
    to be invoked as a command.

    This decorator can be invoked in one of two ways:
    .. code-block:: python3

        # way 1 - no args
        @command
        async def ping(self, ctx):
            await ctx.channel.send("Pong!")

        # way 2 - args
        @command(name="pong")
        async def not_ping(self, ctx):
            await ctx.channel.send("Ping!")

    :param name: The name of the command. If this is not specified, it will use the name of the \
        function object.
    :param description: The description of the command. If this is not specified, it will use the \
        first line of the docstring.
    :param aliases: A list of aliases for this command.
    """
    # wrapper function that actually marks the object
    def inner(func):
        func.is_cmd = True
        func.cmd_name = name or func.__name__
        func.cmd_description = description or get_description(func)
        func.cmd_aliases = aliases or []
        return func

    if func is not None:
        return inner(func)

    return inner
