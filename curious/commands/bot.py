"""
Commands bot subclass.
"""
import re
import inspect
import importlib
import typing

import curio

from curious.client import Client
from curious.commands.command import Command
from curious.commands.context import Context
from curious.commands.plugin import Plugin
from curious.dataclasses import Message
from curious.event import EventContext


def splitter(s):
    def replacer(m):
        return m.group(0).replace(" ", "\x00")

    parts = re.sub(r'".+?"', replacer, s).split()
    parts = [p.replace("\x00", " ") for p in parts]
    return parts


class CommandsBot(Client):
    """
    A subclass of Client that supports commands.
    """

    def __init__(self, token: str = None, *,
                 command_prefix: typing.Union[str, typing.Callable[['CommandsBot', Message], str], list]):
        """
        :param token: The bot token.
        :param command_prefix: The command prefix to use for this bot.
            This can either be a string, a list of strings, or a callable that takes the bot and message as arguments.
        """
        super().__init__(token)

        #: The command prefix to use for this bot.
        self._command_prefix = command_prefix

        #: The dictionary of command objects to use.
        self.commands = {}

        #: The dictionary of plugins to use.
        self.plugins = {}

        self._plugin_modules = {}

        # Add the handle_commands as a message_create event.
        self.add_event("message_create", self.handle_commands)

    async def _wrap_context(self, ctx: Context):
        """
        Wraps a context in a safety wrapper.

        This will dispatch `command_exception` when an error happens.
        """
        try:
            await ctx.invoke()
        except Exception as e:
            gw = self._gateways[ctx.event_context.shard_id]
            await self.fire_event("command_error", ctx, e, gateway=gw)

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
        if command_word in self.commands:
            # Create the context object that will be passed in.
            ctx = Context(self, command=self.commands[command_word], message=message,
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
            for alias in command.aliases:
                self.add_command(alias, command)
            self.add_command(command.name, command)

        self.plugins[plugin_class.__name__] = plugin_class

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
            if Plugin not in inherits:
                # Only inspect instances of plugin.
                continue

            # Assume it has a setup method on it.
            result = member.setup(self, *args, **kwargs)
            if inspect.isawaitable(result):
                result = await result

            # Add it to the list of plugins we need to destroy when unloading.
            mod[1].append(self.plugins[member.__name__])

        if len(mod[1]) == 0:
            raise ValueError("Plugin contained no plugin classes (classes that inherit from Plugin)")

        self._plugin_modules = mod

    def command(self, *args, **kwargs):
        """
        Registers a command to the bot.
        """

        def inner(func):
            command = Command(cbl=func, *args, **kwargs)
            self.commands[command.name] = command
            for alias in command.aliases:
                self.commands[alias] = command
            return command

        return inner
