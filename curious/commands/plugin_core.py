"""
The core plugin.

This contains a help command that can be used.
"""

from curious.commands import command, plugin
from curious.commands.context import Context


class _Core(plugin.Plugin):
    name = "Core"
    _include_in_scan = False
    async def _help_without_embeds(self, ctx: Context, command: str = None):
        """
        The default help command without embeds.
        """
        if not command:
            base = f"**Commands:**\n" \
                   f"Use `{ctx.prefix}help <command>` for more information about each command.\n\n"

            for num, plugin in enumerate(ctx.bot.plugins.copy().values()):
                gen = list(ctx.bot.get_commands_for(plugin))
                cmds = sorted(gen, key=lambda c: c.name)

                names = " **|** ".join(f"`{cmd.name}`" for cmd in cmds)
                base += f"**{num + 1}. {plugin.name}**: {names}\n"
            msg = base
        else:
            initial_name = command
            parts = command.split(" ")
            command = parts[0]

            # get the initial command object
            command_obb = ctx.bot.get_command(command)
            if command_obb:
                for token in parts[1:]:
                    command = token
                    command_obb = command_obb.find_subcommand(token)
                    if command_obb is None:
                        # exit early
                        break

            if command_obb is None:
                msg = "Command not found."
            else:
                base = command_obb.get_usage(ctx, initial_name) + "\n\n"
                base += command_obb.get_help(ctx, initial_name)
                msg = f"```{base}```"

        await ctx.message.channel.send(msg)

    @command(name="help", overridable=True)
    async def _help_command(self, ctx: Context, *, command_for_help: str=None):
        """
        Displays help for a command.
        """
        await self._help_without_embeds(ctx, command_for_help)
