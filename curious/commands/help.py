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
Home of the default help command.

.. currentmodule:: curious.commands.help
"""
import inspect

from curious.commands.context import Context, current_command_context
from curious.commands.exc import CommandsError
from curious.commands.utils import get_full_name, get_usage


async def _get_command_list(ctx: Context, command, *, include_root: bool = True):
    """
    Recursively produces a command list for the command, using subcommands.
    """
    try:
        if not (await ctx.can_run(command)).success:
            return []
    except CommandsError:
        return []

    # XXX: Don't add command names if they're subcommands.
    if not command.cmd_subcommand and include_root:
        c_list = [command.cmd_name]
    else:
        c_list = []

    for subcommand in command.cmd_subcommands:
        # don't do hidden subcommands
        if getattr(subcommand, "cmd_hidden", False) is True:
            continue

        # only do subcommands that can be ran
        try:
            res = await ctx.can_run(subcommand)
            can_run = res.success
        except CommandsError:
            can_run = False

        if not can_run:
            continue

        if include_root:
            c_list.append(get_full_name(subcommand))
        else:
            c_list.append(subcommand.cmd_name)
        c_list.extend(await _get_command_list(ctx, subcommand))

    return c_list


async def _get_command_list_from_plugin(ctx: Context, plugin):
    """
    Gets the command list from a plugin.
    """
    cmds = plugin._get_commands()
    subcommands = [await _get_command_list(ctx, i) for i in cmds]
    return [i for sublist in subcommands for i in sublist]


async def help_for_all(ctx: Context):
    """
    Gets the content of help for all.
    """
    # rows is a list of messages for a help row
    rows = []
    # row_num is the current number to put on a row
    # this isn't incremented if we skip a row
    row_num = 0

    for (plugin, _) in ctx.manager.plugins.values():
        commands = plugin._get_commands()
        command_names = []

        for command in commands:
            # check for hidden annotation
            if getattr(command, "cmd_hidden", False) is True:
                continue

            # don't add subcommands on their own
            # they are detected automatically by the command list loader
            if command.cmd_subcommand:
                continue

            names = await _get_command_list(ctx, command)
            command_names.extend(names)

        if not command_names:
            continue

        row_num += 1
        # wrap the command names in backticks
        # and join it all up with some pipes
        names_joined = " | ".join(f"`{c}`" for c in command_names)
        plugin_name = getattr(plugin, "plugin_name", plugin.__class__.__name__)
        rows.append(f"**{row_num}. {plugin_name}:** {names_joined}")

    # add any uncategorized commands
    if ctx.manager.commands:
        command_names = []

        for command in ctx.manager.commands.values():
            if getattr(command, "cmd_hidden", False) is True:
                continue

            if command.cmd_subcommand:
                continue

            names = await _get_command_list(ctx, command)
            command_names.extend(names)

        if command_names:
            row_num += 1
            names_joined = " | ".join(f"`{c}`" for c in command_names)
            rows.append(f"**{row_num}. Uncategorized:** {names_joined}")

    if not rows:
        return "**You cannot run any commands.**"

    # add a preamble
    preamble = "**Commands:**\nUse `help <command>` for more information about a command.\n\n"

    rows_joined = "\n".join(rows)
    return f"{preamble}{rows_joined}"


async def help_for_one(ctx: Context, command):
    """
    Gets the content of help for one command.
    """
    # try and find a plugin
    plugin = ctx.manager.plugins.get(command)
    if plugin is not None:
        description = inspect.getdoc(plugin)
        subcommands = await _get_command_list_from_plugin(ctx, plugin)
        preamble = f"**Plugin {command}:**\n\n"
    else:
        # get the command from the manager
        cfunc = ctx.manager.get_command(command)
        if cfunc is None:
            return f"No such command: **`{command}`**"

        usage = get_usage(cfunc, invoked_as=command)
        preamble = f"`{usage}`\n\n"
        subcommands = await _get_command_list(ctx, cfunc, include_root=False)

        description = inspect.getdoc(cfunc)

    if description is None:
        description = "No description."

    if subcommands:
        subcommands_fmtted = " | ".join(f"`{x}`" for x in subcommands)
        return f"{preamble}{description}\n\n**Subcommands:** {subcommands_fmtted}"
    else:
        return f"{preamble}{description}"


async def help_command(*, command: str = None):
    """
    The default help command.
    """
    ctx = current_command_context.get()

    if command is None:
        # Let the ruling classes tremble at a Communistic revolution.
        # The proletarians have nothing to lose but their chains. They have a world to win.
        content = await help_for_all(ctx)
    else:
        # Evidence-based policy
        content = await help_for_one(ctx, command)

    await ctx.channel.messages.send(content)
