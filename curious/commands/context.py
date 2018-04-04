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
Class for the commands context.

.. currentmodule:: curious.commands.context
"""
import inspect
import types
from typing import Any, Callable, List, Tuple, Type, Union

import typing_inspect

from curious.commands.converters import convert_channel, convert_float, convert_int, convert_list, \
    convert_member, convert_role, convert_union
from curious.commands.exc import CommandInvokeError, CommandsError, ConditionsFailedError
from curious.commands.utils import _convert
from curious.core.event import EventContext
from curious.dataclasses.channel import Channel
from curious.dataclasses.guild import Guild
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.role import Role
from curious.dataclasses.user import User


class Context(object):
    """
    A class that represents the context for a command.
    """
    _converters = {
        Channel: convert_channel,
        Member: convert_member,
        Role: convert_role,
        # Guild: _convert_guild,
        List: convert_list,
        Union: convert_union,
        str: lambda ann, ctx, arg: arg,
        int: convert_int,
        float: convert_float,
    }

    def __init__(self, message: Message, event_context: EventContext):
        """
        :param message: The :class:`.Message` this command was invoked with.
        :param event_context: The EventContext for this context.
        """
        #: The message for this context.
        self.message = message  # type: Message

        #: The extracted command name for this context.
        self.command_name = None  # type: str

        #: The tokens for this context.
        self.tokens = []  # type: List[str]

        #: The formatted command for this context.
        self.formatted_command = None  # type: str

        #: The plugin for this context.
        self.plugin = None

        #: The manager for this context.
        self.manager = None

        #: The event context for this context.
        self.event_context = event_context  # type: EventContext

        #: The :class:`.Client` for this context.
        self.bot = event_context.bot

    @classmethod
    def add_converter(cls, type_: Type[Any], converter: 'Callable[[Context, str], Any]'):
        """
        Adds a converter to the mapping of converters.

        :param type_: The type to convert to.
        :param converter: The converter callable.
        """
        cls._converters[type_] = converter

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
        # don't match subcommands
        if func.cmd_subcommand:
            return False

        # match on name
        if self.command_name == func.cmd_name:
            return True

        # match on alias
        if self.command_name in func.cmd_aliases:
            return True

        # no match
        return False

    def _lookup_converter(self, annotation: Type[Any]) -> 'Callable[[Any, Context, str], Any]':
        """
        Looks up a converter for the specified annotation.
        """
        origin = typing_inspect.get_origin(annotation)
        if origin is not None:
            annotation = origin

        if annotation in self._converters:
            return self._converters[annotation]

        if annotation is inspect.Parameter.empty:
            return lambda ann, ctx, i: i

        # str etc
        if callable(annotation):
            return annotation

        return lambda ann, ctx, i: i

    async def _get_converted_args(self, func) -> Tuple[tuple, dict]:
        """
        Gets the converted args and kwargs for this command, based on the tokens.
        """
        return await _convert(self, self.tokens, inspect.signature(func))

    def _make_reraise_ctx(self, new_name: str) -> EventContext:
        """
        Makes a new :class:`.EventContext` for re-dispatching.
        """
        return EventContext(self.bot, self.event_context.shard_id, new_name)

    async def _safety_wrapper(self, coro) -> None:
        """
        Runs a command in a safety wrapper.
        """
        evt_ctx = self._make_reraise_ctx("command_error")
        try:
            await coro
        except CommandsError as e:
            await self.manager.client.events.fire_event("command_error", self, e,
                                                        ctx=evt_ctx)
        except Exception as e:
            try:
                raise CommandInvokeError(self) from e
            except CommandInvokeError as e2:
                await self.manager.client.events.fire_event("command_error", self, e2,
                                                            ctx=evt_ctx)

    async def can_run(self, cmd) -> Tuple[bool, list]:
        """
        Checks if a command can be ran.

        :return: If it can be ran, and a list of conditions that failed.
        """
        conditions = getattr(cmd, "cmd_conditions", [])
        failed = []
        for condition in conditions:
            try:
                success = condition(self)
                if inspect.isawaitable(success):
                    success = await success
            except CommandsError:
                raise
            except Exception:
                failed.append(condition)
            else:
                if not success:
                    failed.append(success)

        if failed:
            return False, failed

        return True, []

    async def invoke(self, command) -> Any:
        """
        Invokes a command.
        This will convert arguments, pass them in to the command, and run the command.

        :param command: The command function to run.
        """
        # try and do a group lookup
        # how this works:
        # 1) it checks for the current command's subcommands
        # 1a) if empty, it assumes the current matched command is the best we can do
        #     and exits loop
        # 1b) if not empty, it checks all the subcommands for the current command
        # 2) when checking, it checks if the name of the subcommand matches
        # 3a) if it does, set current_command and matched_command, go back to 1
        # 3b) if it doesn't, exit loop so that current_command is the parent command
        matched_command = command
        current_command = command
        # used for subcommands only
        self_ = None
        if hasattr(current_command, "__self__"):
            self_ = current_command.__self__

        self.plugin = self_

        while True:
            if not current_command.cmd_subcommands:
                break

            if not self.tokens:
                break

            token = self.tokens[0]
            for command in current_command.cmd_subcommands:
                if command.cmd_name == token or token in command.cmd_aliases:
                    matched_command = command
                    current_command = command
                    # update tokens so that they're consumed
                    self.tokens = self.tokens[1:]
                    break
            else:
                # we didnt match any subcommand
                # so escape the loop now
                break

        # bind method, if appropriate
        if not hasattr(matched_command, "__self__") and self_ is not None:
            matched_command = types.MethodType(matched_command, self_)

        # check if we can actually run it
        can_run, conditions_failed = await self.can_run(matched_command)
        if not can_run:
            raise ConditionsFailedError(self, conditions_failed)

        # check if we're ratelimited
        await self.manager.ratelimiter.ensure_ratelimits(self, matched_command)

        # convert all the arguments into the command
        converted_args, converted_kwargs = await self._get_converted_args(matched_command)

        # finally, spawn the new command task
        try:
            return await matched_command(self, *converted_args, **converted_kwargs)
        except CommandsError:
            raise
        except Exception as e:
            raise CommandInvokeError(self) from e

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
            ev_ctx = self._make_reraise_ctx("command_error")
            try:
                return await self.invoke(to_invoke)
            except CommandsError as e:
                await self.manager.client.events.fire_event("command_error", self, e, ctx=ev_ctx)
