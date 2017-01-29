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
from curious.commands.plugin_core import _Core
from curious.dataclasses.message import Message
from curious.dataclasses.embed import Embed
from curious.event import EventContext
from curious.util import attrdict


def split_message_content(content: str, delim: str = " ") -> typing.List[str]:
    """
    Splits a message into individual parts by `delim`, returning a list of strings.
    This method preserves quotes.

    :param content: The message content to split.
    :param delim: The delimiter to split on.
    :return: A list of items split
    """

    def replacer(m):
        return m.group(0).replace(delim, "\x00")

    parts = re.sub(r'".+?"', replacer, content).split()
    parts = [p.replace("\x00", " ") for p in parts]
    return parts


def _default_msg_func_factory(prefix: str):
    def __inner(bot: CommandsBot, message: Message):
        matched = None
        match = False
        if isinstance(prefix, str):
            match = message.content.startswith(prefix)
            if match:
                matched = prefix

        elif isinstance(prefix, list):
            for i in prefix:
                if message.content.startswith(i):
                    matched = i
                    match = True
                    break

        if not matched:
            return None

        tokens = split_message_content(message.content[len(matched):])
        command_word = tokens[0]

        return command_word, tokens[1:], matched

    __inner.prefix = prefix
    return __inner


class CommandsBot(Client):
    """
    A subclass of Client that supports commands.
    """

    def __init__(self, token: str = None, *,
                 command_prefix: typing.Union[str, list] = None,
                 message_check: typing.Callable[['CommandsBot', Message], bool] = None,
                 description: str = "The default curious description"):
        """
        :param token: The bot token.
        :param command_prefix: The command prefix to use for this bot.
            This can either be a string, a list of strings, or a callable that takes the bot and message as arguments.
        :param description: The description of this bot.
        """
        super().__init__(token)
        if not command_prefix and not message_check:
            raise TypeError("Must provide one of `command_prefix` or `message_check`")

        self._message_check = message_check or _default_msg_func_factory(command_prefix)

        #: The description of this bot.
        self.description = description

        #: The dictionary of command objects to use.
        self.commands = attrdict()

        #: The dictionary of plugins to use.
        self.plugins = {}

        self._plugin_modules = {}

        # Add the handle_commands as a message_create event.
        self.add_event("message_create", self.handle_commands)
        self.add_plugin(_Core(self))
        #self.add_command("help", Command(cbl=_help, name="help"))

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
            self.remove_event("command_error", self.on_command_error)
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

        # use the message check function
        _ = self._message_check(self, message)
        if inspect.isawaitable(_):
            _ = await _

        if not _:
            # not a command, do not bother
            return

        # func should return command_word and args for the command
        command_word, args, prefix = _
        command = self.get_command(command_word)
        if command is None:
            return

        # Create the context object that will be passed in.
        ctx = Context(self, command=command, message=message,
                      event_ctx=event_ctx)
        ctx.prefix = prefix
        ctx.name = command_word
        ctx.raw_args = args

        await curio.spawn(self._wrap_context(ctx))

    def add_command(self, command_name: str, command: Command):
        """
        Adds a command to the internal registry of commands.

        :param command_name: The name of the command to add.
        :param command: The command object to add.
        """
        if command_name in self.commands:
            if not self.commands[command_name]._overridable:
                raise ValueError("Command {} already exists".format(command_name))
            else:
                self.commands.pop(command_name)

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

            if not hasattr(member, "__dict__"):
                # don't be difficult
                continue

            # evil cpython type implementation detail abuse
            if member.__dict__.get("_include_in_scan", True) is False:
                # this won't show up for subclasses.
                # so they always have to be explicitly set
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
                # not a plugin event
                if not hasattr(event, "plugin"):
                    continue
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
            return cmd.can_be_invoked_by(command_name)

        f = filter(_f, self.commands.values())
        return next(f, None)
