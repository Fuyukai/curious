"""
Class for the commands context.
"""
import inspect
from typing import Any, List, Tuple, Union

from curious.commands.utils import _convert
from curious.core.event import EventContext
from curious.dataclasses.channel import Channel
from curious.dataclasses.guild import Guild
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.user import User


class Context(object):
    """
    A class that represents the context for a command.
    """
    _converters = {
        # Channel: _convert_channel,
        # Member: _convert_member,
        # Guild: _convert_guild,
        str: lambda ctx, tokens: tokens,
        # int: _convert_int,
        # float: _convert_float,
    }

    def __init__(self, message: Message, event_context: EventContext):
        """
        :param message: The :class:`.Message` this command was invoked with.
        """
        #: The message for this context.
        self.message: Message = message

        #: The extracted command name for this context.
        self.command_name: str = None

        #: The tokens for this context.
        self.tokens: List[str] = []

        #: The formatted command for this context.
        self.formatted_command: str = None

        #: The plugin for this context.
        self.plugin = None

        #: The manager for this context.
        self.manager = None

        #: The event context for this context.
        self._event_context: EventContext = event_context

        #: The :class:`.Client` for this context.
        self.bot = event_context.bot

    @property
    def guild(self) -> Guild:
        """
        :return: The :class:`.Guild` for this context, or None.
        """
        return self.message.guild

    @property
    def channel(self) -> Channel:
        """
        :return: The :class:`.Channel` for this context.
        """
        return self.message.channel

    @property
    def author(self) -> Union[Member, User]:
        """
        :return: The :class:`.Member` or :class:`.User` for this context.
        """
        return self.message.author

    def match_command(self, func) -> bool:
        """
        Attempts to match a command with this context.
        """
        if self.command_name == func.cmd_name:
            return True

        if self.command_name in func.cmd_aliases:
            return True

        return False

    def _lookup_converter(self, annotation):
        """
        Looks up a converter for the specified annotation.
        """
        if annotation in self._converters:
            return self._converters[annotation]

        if callable(annotation):
            return annotation

    async def _get_converted_args(self, func) -> Tuple[tuple, dict]:
        """
        Gets the converted args and kwargs for this command, based on the tokens.
        """
        return await _convert(self, self.tokens, inspect.signature(func))

    async def invoke(self, command) -> Any:
        """
        Invokes a command.
        This will convert arguments, pass them in to the command, and run the command.

        :param command: The command function to run.
        """
        # this is probably a bound method
        # so we can copy the plugin straight to us
        self.plugin = command.__self__

        # convert all the arguments into the command
        converted_args, converted_kwargs = await self._get_converted_args(command)

        return await command(self, *converted_args, **converted_kwargs)

    async def try_invoke(self) -> Any:
        """
        Attempts to invoke the command, using the specified manager.

        This will scan all the commands, then invoke as appropriate.
        """
        # temp variable used to invoke if applicable
        to_invoke = None

        for command in self.manager.commands.values():
            if self.match_command(command):
                to_invoke = command
                break

        for plugin in self.manager.plugins.values():
            commands = plugin._get_commands()
            for command in commands:
                if self.match_command(command):
                    to_invoke = command
                    break

        if to_invoke is not None:
            return await self.invoke(to_invoke)
