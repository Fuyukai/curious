"""
Home of the default help command.
"""
import inspect

from curious.commands import Context
from curious.commands.exc import CommandsError
from curious.commands.utils import get_full_name, get_usage


async def _get_command_list(ctx: Context, command):
    """
    Recursively produces a command list for the command, using subcommands.
    """
    try:
        if not (await ctx.can_run(command))[0]:
            return []
    except CommandsError:
        return []

    # XXX: Don't add command names if they're subcommands.
    if not command.cmd_subcommand:
        l = [command.cmd_name]
    else:
        l = []

    for subcommand in command.cmd_subcommands:
        # don't do hidden subcommands
        if getattr(subcommand, "cmd_hidden", False) is True:
            continue

        # only do subcommands that can be ran
        try:
            can_run, _ = await ctx.can_run(command)
        except CommandsError:
            can_run = False

        if not can_run:
            continue

        l.append(get_full_name(subcommand))
        l.extend(await _get_command_list(ctx, subcommand))

    return l


async def help_for_all(ctx: Context):
    """
    Gets the content of help for all.
    """
    # rows is a list of messages for a help row
    rows = []
    # row_num is the current number to put on a row
    # this isn't incremented if we skip a row
    row_num = 0

    for plugin in ctx.manager.plugins.values():
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
        names_joined = ' | '.join(f"`{c}`" for c in command_names)
        plugin_name = getattr(plugin, "plugin_name", plugin.__class__.__name__)
        rows.append(f"**{row_num}. {plugin_name}:** {names_joined}")

    # add any uncategorized commands
    if ctx.manager.commands:
        command_names = []

        for command in ctx.manager.commands.values():
            if command.cmd_subcommand:
                continue

            names = await _get_command_list(ctx, command)
            command_names.extend(names)

        if command_names:
            row_num += 1
            names_joined = ' | '.join(f"`{c}`" for c in command_names)
            rows.append(f"**{row_num}. Uncategorized:** {names_joined}")

    if not rows:
        return "**You cannot run any commands.**"

    # add a preamble
    preamble = "**Commands:**\nUse `help <command>` for more information about a command.\n\n"

    rows_joined = '\n'.join(rows)
    return f"{preamble}{rows_joined}"


async def help_for_one(ctx: Context, command):
    """
    Gets the content of help for one command.
    """
    # get the command from the manager
    cfunc = ctx.manager.get_command(command)
    if cfunc is None:
        return "**No such command.**"

    usage = get_usage(cfunc, invoked_as=command)
    description = inspect.getdoc(cfunc)
    if description is None:
        return f"`{usage}`"

    return f"`{usage}`\n\n{description}"


async def help_command(ctx: Context, *, command: str = None):
    """
    The default help command.
    """
    if command is None:
        # Let the ruling classes tremble at a Communistic revolution.
        # The proletarians have nothing to lose but their chains. They have a world to win.
        content = await help_for_all(ctx)
    else:
        # Evidence-based policy
        content = await help_for_one(ctx, command)

    await ctx.channel.send(content)
