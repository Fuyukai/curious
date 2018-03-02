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
import inspect
import logging
from typing import Any, List, Type

from curious.commands import plugin as md_plugin
from curious.commands.ratelimit import BucketNamer, CommandRateLimit
from curious.commands.utils import get_description

logger = logging.getLogger(__name__)


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
        def set(attr: str, value: Any):
            try:
                return getattr(func, attr)
            except AttributeError:
                setattr(func, attr, value)

        set("is_cmd", True)
        set("cmd_name", name or func.__name__)
        set("cmd_description", description or get_description(func))
        set("cmd_aliases", aliases or [])
        set("cmd_subcommand", False)
        set("cmd_subcommands", [])
        set("cmd_parent", None)
        set("cmd_hidden", hidden)
        set("cmd_conditions", [])
        set("cmd_ratelimits", [])

        # annotate command object with any extra
        for ann_name, annotation in kwargs.items():
            ann_name = "cmd_" + name
            set(ann_name, annotation)

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
            if not hasattr(parent, "is_cmd"):
                raise TypeError("Cannot be a subcommand of a non-command")

            cmd = command(**kwargs)(func)
            cmd.cmd_subcommand = True
            cmd.cmd_parent = parent
            parent.cmd_subcommands.append(cmd)
            return cmd

        return inner_2

    return inner


def autoplugin(plugin: 'Type[md_plugin.Plugin]' = None, *,
               startswith: str = "command") -> 'Type[md_plugin.Plugin]':
    """
    Automatically assigns commands inside a plugin.

    This will scan a :class:`.Plugin` for functions matching the pattern ``command_[parent_]name``,
    and automatically decorate them with the command decorator and subcommand decorators.

    :param plugin: The :class:`.Plugin` subclass to autoplugin.
    :param startswith: Used to override what the command function prefix will be.
    :return: The edited plugin.
    """
    # we were called like @autoplugin(startswith="something")
    # so return a lambda that provides the plugin
    if plugin is None:
        return lambda plugin: autoplugin(plugin, startswith=startswith)

    if not issubclass(plugin, md_plugin.Plugin):
        raise ValueError(f"Cannot autoplugin an object of type non-PluginMeta ({type(plugin)})")

    # we were called like @autoplugin or the lambda above completed
    logger.debug("Processing autocommand for plugin type %s", plugin.__name__)
    for name, member in plugin.__dict__.copy().items():
        if not name.startswith(startswith + "_"):
            continue

        # unwrap all functions
        member = inspect.unwrap(member)

        parts = name.split("_", 2)
        if len(parts) == 2:  # regular command, no parent
            # wrap it in a command and continue
            made_command = command(name=parts[1])(member)
            logger.debug("Made a top-level command %s on plugin %s", parts[1], plugin.__name__)
            setattr(plugin, name, made_command)
        else:
            # we have a parent, so call parent.subcommand() on it instead
            parent = parts[1]

            # o(n2) loop!
            def _pred(i):
                return hasattr(i, "cmd_name") and i.cmd_name == parent

            for _, found_command in inspect.getmembers(plugin, predicate=_pred):
                break
            else:
                raise AttributeError(
                    f"When doing an autoplugin, could not locate parent command {parent}.\n"
                    f"You need to make sure that the parent A) exists and B) is before the "
                    f"current command in the class definition for the autoplugin to resolve the "
                    f"name properly."
                ) from None

            made_command = found_command.subcommand(name=parts[2])(member)
            logger.debug("Made a subcommand %s (parent %s) on plugin %s",
                         parts[2], parts[1], plugin.__name__)
            setattr(plugin, name, made_command)

    return plugin
