"""
The base class for a plugin.
"""
import typing

from curious.commands import bot as c_bot
from curious.commands.command import Command
from curious.commands.context import Context


class Plugin(object):
    def __init__(self, bot: 'c_bot.CommandsBot'):
        self.bot = bot

    async def load(self):
        """
        Called just after the plugin has loaded, before any commands have been registered. Used for async loading.
        """

    async def unload(self):
        """
        Called just before the plugin is to be unloaded, after all commands have been removed.
        """

    async def plugin_check(self, ctx: Context):
        """
        Added as a check for every command in this plugin.
        """

    def _scan_body(self) -> typing.Tuple[list, list]:
        """
        Scans the body of this type for events and commands.

        :return: Two lists, the first one containing events and the second one containing commands.
        """
        events = []
        commands = []

        for name, value in self.__dict__.items():
            if isinstance(value, Command):
                commands.append(value)

            elif hasattr(value, "event"):
                name = getattr(value, "event")
                events.append((name, value))

        return events, commands

    @classmethod
    def setup(cls, bot: 'c_bot.CommandsBot', *args, **kwargs):
        """
        Default setup function for a plugin.

        This will create a new instance of the class, then add it as a Plugin to the bot.
        """
        instance = cls(bot, *args, **kwargs)
        bot.add_plugin(instance)
