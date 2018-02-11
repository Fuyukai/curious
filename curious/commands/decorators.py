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
Decorators to annotate function objects.

.. currentmodule:: curious.commands.decorators
"""
from typing import List

from curious.commands.ratelimit import BucketNamer, CommandRateLimit
from curious.commands.utils import get_description


def command(*,
            name: str = None, description: str = None,
            hidden: bool = False,
            aliases: List[str] = None, **kwargs):
    """
    Marks a function as a command. This annotates the command with some attributes that allow it
    to be invoked as a command.

    This decorator can be invoked like this:

    .. code-block:: python3

        @command()
        async def ping(self, ctx):
            await ctx.channel.messages.send("Ping!")

    :param name: The name of the command. If this is not specified, it will use the name of the \
        function object.
    :param description: The description of the command. If this is not specified, it will use the \
        first line of the docstring.
    :param hidden: If this command is hidden; i.e. it doesn't show up in the help listing.
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
        func.cmd_hidden = hidden
        func.cmd_conditions = getattr(func, "cmd_conditions", [])
        func.cmd_ratelimits = getattr(func, "cmd_ratelimits", [])

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


def ratelimit(*, limit: int, time: float, bucket_namer=BucketNamer.AUTHOR):
    """
    Adds a ratelimit to a command.
    """
    def inner(func):
        if not hasattr(func, "cmd_ratelimits"):
            func.cmd_ratelimits = []

        rl = CommandRateLimit(limit=limit, time=time, bucket_namer=bucket_namer)
        rl.command = func
        func.cmd_ratelimits.append(rl)
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

