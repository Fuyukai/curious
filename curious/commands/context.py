"""
Defines :class:`.Context`.
"""

import typing

from curious.core import client as cl
from curious.core.event import EventContext
from curious.dataclasses import channel as dt_channel, guild as dt_guild, member as dt_member, message as dt_message, \
    user as dt_user, webhook as dt_webhook


class Context(object):
    """
    Represents a context object.

    :ivar prefix: The prefix that was used to invoke this command.
    :ivar name: The name of the command that was invoked.
        This is useful for commands with multiple aliases.
    :ivar bot: The bot instance that is handling this command.
    :ivar message: The message object that was used to invoke this command.
    :ivar command: The command that is currently being invoked.
    :ivar raw_args: The raw split arguments of the message.
    """

    def __init__(self, client: 'cl.Client', message: 'dt_message.Message',
                 command, event_ctx):
        """
        :param client: The client associated with this message.
        :param message: The message object that was used to invoke this command.
        :param command: The command that is currently being invoked.
        """
        self.bot = client
        self.message = message
        self.command = command

        self.prefix = None  # type: str
        self.name = None  # type: str

        self.raw_args = None  # type: typing.List[str]

        self.event_context = event_ctx  # type: EventContext

    async def invoke(self):
        """
        Invokes the underlying command object using the args provided.
        """
        await self.command.invoke(self, *self.raw_args)

    @property
    def channel(self) -> 'dt_channel.Channel':
        """
        :return: The :class:`Channel` this context was invoked in. 
        """
        return self.message.channel

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`Guild` this context was invoked in. 
        """
        return self.message.guild

    @property
    def author(self) -> 'typing.Union[dt_member.Member, dt_user.User, dt_webhook.Webhook]':
        """
        :return: The :class:`Member` that invoked this command.
        """
        return self.message.author
