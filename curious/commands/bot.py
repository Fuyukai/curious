"""
Commands bot subclass.
"""
import random
import re
import inspect
import importlib
import traceback
import typing

import curio
import sys

from curious.client import Client
from curious.commands.command import Command
from curious.commands.context import Context
from curious.commands.plugin import Plugin
from curious.dataclasses import Message
from curious.dataclasses.embed import Embed
from curious.event import EventContext


def splitter(s):
    def replacer(m):
        return m.group(0).replace(" ", "\x00")

    parts = re.sub(r'".+?"', replacer, s).split()
    parts = [p.replace("\x00", " ") for p in parts]
    return parts


async def _help_with_embeds(ctx: Context, command: str = None):
    """
    The default help command, but with embeds!
    """
    if not command:
        em = Embed(title=ctx.bot.description)
        em.description = "Type {}help <command> for more information.".format(ctx.prefix)

        for plugin in ctx.bot.plugins.copy().values():
            gen = list(ctx.bot.get_commands_for(plugin))
            cmds = sorted(gen, key=lambda c: c.name)

            names = []
            for cmd in cmds:
                failed, result = await cmd.can_run(ctx)
                if not failed:
                    names.append("`{}`".format(cmd.name))

            names = "\n".join(names)
            if not names:
                continue

            em.add_field(name=plugin.name, value=names)

    else:
        command_obb = ctx.bot.get_command(command)  # type: Command
        if not command_obb:
            em = Embed(title=command, description="Command not found.", colour=0xe74c3c)
        else:
            if command_obb.name != command:
                title = "{} (alias for `{}`)".format(command, command_obb.name)
            else:
                title = command_obb.name
            em = Embed(title=title)
            em.description = command_obb.get_help(ctx, command)  # Stop. Get help.

            if len(command_obb.aliases) != 1:
                b = "\n".join("`{}`".format(n) for n in command_obb.aliases if n != command)
                em.add_field(name="Aliases", value=b)

            # Check if they can run the command.
            if len(command_obb.invokation_checks) > 0:
                failed, result = await command_obb.can_run(ctx)
                if failed:
                    em.description += "\n\nYou **cannot** run this command. (`{}` checks failed.)".format(failed)
                    em.colour = 0xFF0000

            usage = command_obb.get_usage(ctx, command)
            em.add_field(name="Usage", value=usage)

    if not em.colour:
        em.colour = random.randrange(0, 0xFFFFFF)

    await ctx.channel.send(embed=em)


async def _help_without_embeds(ctx: Context, command: str = None):
    """
    The default help command without embeds.
    """
    if not command:
        base = "**Commands:**\nUse `{}help <command>` for more information about each command.\n\n".format(ctx.prefix)

        for num, plugin in enumerate(ctx.bot.plugins.copy().values()):
            gen = list(ctx.bot.get_commands_for(plugin))
            cmds = sorted(gen, key=lambda c: c.name)

            names = " **|** ".join("`{}`".format(cmd.name) for cmd in cmds)
            base += "**{}. {}**: {}\n".format(num + 1, plugin.name, names)

        msg = base
    else:
        command_obj = ctx.bot.get_command(command)
        if command_obj is None:
            msg = "Command not found."
        else:
            if command_obj.name != command:
                title = "{} (alias for `{}`)".format(command, command_obj.name)
            else:
                title = command_obj.name

            base = "{}{}\n\n".format(ctx.prefix, title)
            base += "{}".format(command_obj.get_help())
            msg = "```{}```".format(base)

    msg += "\n**For a better help command, give the bot Embed Links permission.**"

    await ctx.message.channel.send(msg)


async def _help(ctx: Context, *, command: str = None):
    """
    The default help command.
    """
    if not ctx.channel.permissions(ctx.guild.me).embed_links:
        # no embeds :(
        await _help_without_embeds(ctx, command)
    else:
        await _help_with_embeds(ctx, command)


class CommandsBot(Client):
    """
    A subclass of Client that supports commands.
    """

    def __init__(self, token: str = None, *,
                 command_prefix: typing.Union[str, typing.Callable[['CommandsBot', Message], str], list],
                 description: str = "The default curious description"):
        """
        :param token: The bot token.
        :param command_prefix: The command prefix to use for this bot.
            This can either be a string, a list of strings, or a callable that takes the bot and message as arguments.
        :param description: The description of this bot.
        """
        super().__init__(token)

        #: The command prefix to use for this bot.
        self._command_prefix = command_prefix

        #: The description of this bot.
        self.description = description

        #: The dictionary of command objects to use.
        self.commands = {}

        #: The dictionary of plugins to use.
        self.plugins = {}

        self._plugin_modules = {}

        # Add the handle_commands as a message_create event.
        self.add_event("message_create", self.handle_commands)
        self.add_command("help", Command(cbl=_help, name="help"))

    async def _wrap_context(self, ctx: Context):
        """
        Wraps a context in a safety wrapper.

        This will dispatch `command_exception` when an error happens.
        """
        try:
            await ctx.invoke()
        except Exception as e:
            gw = self._gateways[ctx.event_context.shard_id]
            await self.fire_event("command_error", e, ctx=ctx, gateway=gw)

    async def on_command_error(self, ctx, e):
        """
        Default error handler.

        This is meant to be overriden - normally it will just print the traceback.
        """
        if len(self.events.getall("command_error")) >= 2:
            # remove ourselves
            self.remove_event("command_errr", self.on_command_error)
            return

        traceback.print_exception(None, e, e.__traceback__)

    async def handle_commands(self, event_ctx: EventContext, message: Message):
        """
        Handles invokation of commands.

        This is added as an event during initialization.
        """
        if not message.content:
            # Minor optimization - don't fire on empty messages.
            return

        command_prefix = self._command_prefix
        if isinstance(command_prefix, str):
            command_prefix = [command_prefix]

        if callable(command_prefix):
            command_prefix = command_prefix(self, message)

        if inspect.isawaitable(command_prefix):
            command_prefix = await command_prefix
        # Check if the prefix matches.
        # If so, break the loop, which will set the prefix variable to the one that matched.
        for prefix in command_prefix:
            if message.content.startswith(prefix):
                break
        else:
            return

        non_prefix_content = message.content[len(prefix):]

        # Split the message out
        tokens = splitter(non_prefix_content)

        # Split out the command word from the command prefix.
        command_word = tokens[0]

        command = self.get_command(command_word)
        if command is None:
            return

        # Create the context object that will be passed in.
        ctx = Context(self, command=command, message=message,
                      event_ctx=event_ctx)
        ctx.prefix = prefix
        ctx.name = command_word
        ctx.raw_args = tokens[1:]

        await curio.spawn(self._wrap_context(ctx))

    def add_command(self, command_name: str, command: Command):
        """
        Adds a command to the internal registry of commands.

        :param command_name: The name of the command to add.
        :param command: The command object to add.
        """
        if command_name in self.commands:
            raise ValueError("Command {} already exists".format(command_name))

        self.commands[command_name] = command

    def add_plugin(self, plugin_class):
        """
        Adds a plugin to the bot.

        :param plugin_class: The plugin class to add.
        """
        events, commands = plugin_class._scan_body()

        for event in events:
            event.plugin = plugin_class
            self.events.add(event.event, event)

        for command in commands:
            # Bind the command to the plugin.
            command.instance = plugin_class
            # dont add any aliases
            self.add_command(command.name, command)

        self.plugins[plugin_class.name] = plugin_class

    async def load_plugins_from(self, import_name: str, *args, **kwargs):
        """
        Loads a plugin and adds it to the internal registry.

        :param import_name: The import name of the plugin to add (e.g `bot.plugins.moderation`).
        """
        module = importlib.import_module(import_name)
        mod = [module, []]

        # Locate all of the Plugin types.
        for name, member in inspect.getmembers(module):
            if not isinstance(member, type):
                # We only want to inspect instances of type (i.e classes).
                continue

            inherits = inspect.getmro(member)
            # remove `member` from the mro
            # this prevents us registering Plugin as a plugin
            inherits = [i for i in inherits if i != member]
            if Plugin not in inherits:
                # Only inspect instances of plugin.
                continue

            # Assume it has a setup method on it.
            result = member.setup(self, *args, **kwargs)
            if inspect.isawaitable(result):
                result = await result

            # Add it to the list of plugins we need to destroy when unloading.
            # We add the type, not the instance, as the instances are destroyed separately.
            mod[1].append(member)

        if len(mod[1]) == 0:
            raise ValueError("Plugin contained no plugin classes (classes that inherit from Plugin)")

        self._plugin_modules[import_name] = mod

    async def unload_plugins_from(self, import_name: str):
        """
        Unloads plugins from the specified import name.

        This is the opposite to :meth:`load_plugins_from`.
        """
        mod, plugins = self._plugin_modules[import_name]
        # we can't do anything with the module currently because it's still in our locals scope
        # so we have to wait to delete it
        # i'm not sure this is how python imports work but better to be safe
        # (especially w/ custom importers)

        for plugin in plugins:
            # find all the Command instances with this plugin as the body
            for name, command in self.commands.copy().items():
                # isinstance() checks ensures that the type of the instance is this plugin
                if isinstance(command.instance, plugin):
                    # make sure the instance isn't lingering around
                    command.instance = None
                    # rip
                    self.commands.pop(name)

            # remove all events registered
            for name, event in self.events.copy().items():
                if isinstance(event.plugin, plugin):
                    event.plugins = None
                    self.remove_event(name, event)

            # now that all commands are dead, call `unload()` on all of the instances
            for name, instance in self.plugins.copy().items():
                if isinstance(instance, plugin):
                    r = instance.unload()
                    if inspect.isawaitable(r):
                        await r

                    self.plugins.pop(name)

        # remove from sys.modules and our own registry to remove all references
        del sys.modules[import_name]
        del self._plugin_modules[import_name]
        del mod

    def command(self, *args, **kwargs):
        """
        Registers a command to the bot.
        """

        def inner(func):
            command = Command(*args, cbl=func, **kwargs)
            self.commands[command.name] = command
            for alias in command.aliases:
                self.commands[alias] = command
            return command

        return inner

    def get_commands_for(self, plugin: Plugin) -> typing.Generator[Command, None, None]:
        """
        Gets the commands for the specified plugin.

        :param plugin: The plugin instance to get commands of.
        :return: A list of :class:`Command`.
        """
        for command in self.commands.copy().values():
            if command.instance == plugin:
                yield command

    def get_command(self, command_name: str) -> typing.Union[Command, None]:
        """
        Gets a command object for the specified command name.

        :param command_name: The name of the command.
        :return: The command object if found, otherwise None.
        """

        def _f(cmd: Command):
            return cmd.name == command_name or command_name in cmd.aliases

        f = filter(_f, self.commands.values())
        return next(f, None)
