"""
The core plugin.

This contains a help command that can be used.
"""
from curious.dataclasses.embed import Embed

from curious.commands import command, plugin
from curious.commands.context import Context


class _Core(plugin.Plugin):
    name = "Core"
    _include_in_scan = False

    # region embeds
    async def _help_all_with_embeds(self, ctx: Context):
        # display help for all commands
        em = Embed(title=ctx.bot.description)
        if ctx.prefix is not None:
            em.description = "Type {}help <command> for more information.".format(ctx.prefix)
        else:
            em.description = "Use `help <command>` for more information."

        for plugin in ctx.bot.plugins.copy().values():
            gen = list(ctx.bot.get_commands_for(plugin))
            cmds = sorted(gen, key=lambda c: c.name)

            names = []
            for cmd in cmds:
                failed, result = await cmd.can_run(ctx)
                if not failed:
                    names.append("`{}`".format(cmd.name))

            names = ", ".join(names)
            if not names:
                continue

            em.add_field(name=plugin.name, value=names, inline=False)

        return em

    async def _help_for_command_with_embeds(self, ctx: Context, command_for_help: str):
        initial_name = command_for_help
        parts = command_for_help.split(" ")
        command = parts[0]

        # get the initial command object
        command_obb = ctx.bot.get_command(command)
        if command_obb is not None:
            for token in parts[1:]:
                command = token
                command_obb = command_obb.find_subcommand(token)
                if command_obb is None:
                    # exit early
                    break

        if not command_obb:
            em = Embed(title=command, description="Command not found.", colour=0xe74c3c)
        else:
            # Check if this was an alias.
            if command_obb.name != command:
                title = "{} (alias for `{}`)".format(command, command_obb.name)
            else:
                title = command_obb.name
            em = Embed(title=title)
            em.description = command_obb.get_help(ctx, command)  # Stop. Get help.

            # If this has other aliases, add them.
            if len(command_obb.aliases) != 1:
                b = "\n".join("`{}`".format(n) for n in command_obb.aliases if n != command)
                em.add_field(name="Aliases", value=b)

            # Check if they can run the command.
            if len(command_obb.invokation_checks) > 0:
                failed, result = await command_obb.can_run(ctx)
                if failed:
                    em.description += "\n\nYou **cannot** run this command. (`{}` checks failed.)".format(failed)
                    em.colour = 0xFF0000

            usage = command_obb.get_usage(ctx, initial_name)
            em.add_field(name="Usage", value=usage)

            sbb = "\n".join([subcommand.name for subcommand in command_obb.subcommands])
            if sbb:
                em.add_field(name="Subcommands", value=sbb)

        return em

    async def _help_with_embeds(self, ctx: Context, command_for_help: str):
        # help command WITH embeds
        if command_for_help is None:
            embed = await self._help_all_with_embeds(ctx)
        else:
            embed = await self._help_for_command_with_embeds(ctx, command_for_help)

        await ctx.channel.send(embed=embed)

    # endregion

    async def _help_without_embeds(self, ctx: Context, command: str = None):
        """
        The default help command without embeds.
        """
        if not command:
            base = "**Commands:**\nUse `{}help <command>` for more information about each command.\n\n".format(
                ctx.prefix)

            for num, plugin in enumerate(ctx.bot.plugins.copy().values()):
                gen = list(ctx.bot.get_commands_for(plugin))
                cmds = sorted(gen, key=lambda c: c.name)

                names = " **|** ".join("`{}`".format(cmd.name) for cmd in cmds)
                base += "**{}. {}**: {}\n".format(num + 1, plugin.name, names)

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
                base += "{}".format(command_obb.get_help(ctx, initial_name))
                msg = "```{}```".format(base)

        msg += "\n**For a better help command, give the bot Embed Links permission.**"

        await ctx.message.channel.send(msg)

    @command(name="help", overridable=True)
    async def _help_command(self, ctx: Context, *, command_for_help: str=None):
        """
        Displays help for a command.
        """
        if ctx.channel.permissions(ctx.guild.me).embed_links:
            await self._help_with_embeds(ctx, command_for_help)
        else:
            await self._help_without_embeds(ctx, command_for_help)

