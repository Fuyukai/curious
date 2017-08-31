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

            num = 0
            for plugin in ctx.bot.plugins.copy().values():
                cmds = sorted(list(ctx.bot.get_commands_for(plugin)), key=lambda c: c.name)

                # check if the command can be ran by this user
                # if they can, its appended to ``can_run``
                # then built instead of the cmds list
                can_run = []
                for command in cmds:
                    cannot, _ = await command.can_run(ctx)
                    if not cannot:
                        can_run.append(command)

                # if can_run is empty this cog cannot be ran
                if not can_run:
                    continue

                # increment the plguin number here
                # so it doesn't go 1. 3. etc if nothing in 2 is runnable by the author
                num += 1

                names = " **|** ".join(f"`{cmd.name}`" for cmd in cmds)
                base += f"**{num}. {plugin.name}**: {names}\n"
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
