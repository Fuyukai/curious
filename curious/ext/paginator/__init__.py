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
A reactions-based paginator.
"""
import typing

import multio

from curious.core.event import ListenerExit
from curious.dataclasses.channel import Channel
from curious.dataclasses.embed import Embed
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.reaction import Reaction
from curious.dataclasses.user import User


class ReactionsPaginator(object):
    """
    A paginator for a message using reactions.
    """
    BUTTON_BACKWARDS = "◀"
    BUTTON_FORWARD = "▶"
    BUTTON_STOP = "⏹"

    def __init__(self, content: typing.Union[str, typing.List[str], typing.List[Embed]],
                 channel: Channel,
                 respond_to: typing.Union[Member, User], *,
                 break_at: int = 2000, title: str = None):
        """
        :param content: The content to page through.
        :param channel: The channel to send the content to.
        :param respond_to: The member to respond
        :param break_at: The number of characters to break the message up into.
        :param title: The title to put above the embed.
        """
        self._content = content
        self.channel = channel
        self.respond_to = respond_to
        self.title = title

        self.bot = self.channel._bot  # hacky af

        # chunk the message up
        if isinstance(content, list):
            self._message_chunks = content
        else:
            self._message_chunks = [self._content[i:i + break_at] for i in
                                    range(0, len(self._content), break_at)]

        #: The current page this paginator is on.
        self.page = 0

        #: The message object that is being edited.
        self._message = None  # type: Message
        self._running = False
        self._reaction_queue = multio.Queue()

    @classmethod
    async def paginate_response(cls, content: str,
                                responding_to: Message, *args, **kwargs) -> 'ReactionsPaginator':
        """
        Paginates a response to a message.

        :param content: The content to paginate.
        :param responding_to: The message object that you are responding to.
        """
        obb = cls(content, responding_to.channel, responding_to.author, *args, **kwargs)
        await obb.paginate()
        return obb

    async def send_current_page(self) -> None:
        """
        Sends the current page to the channel.
        """
        chunk = self._message_chunks[self.page]
        if isinstance(chunk, Embed):
            embed = chunk
        else:
            embed = Embed(description=self._message_chunks[self.page])
            embed.set_footer(text="Page {}/{}".format(self.page + 1, len(self._message_chunks)))

        if self._message is None:
            self._message = await self.channel.messages.send(
                content=self.title,
                embed=embed
            )
        else:
            await self._message.edit(
                new_content=self.title,
                embed=embed
            )

    async def _add_initial_reactions(self):
        """
        Adds the initial reactions to this message.
        """
        await self._message.react(self.BUTTON_BACKWARDS)
        await self._message.react(self.BUTTON_FORWARD)
        await self._message.react(self.BUTTON_STOP)

    async def paginate(self):
        """
        Starts paginating this message.

        This will continuously listen for reactions on this message until the STOP button is
        pressed.
        """
        self._running = True

        async def consume_reaction(ctx, message: Message, author: Member, reaction: Reaction):
            """
            Consumes reaction events and places them on a queue.
            """
            if message.id != self._message.id:
                return

            if author.id != self.respond_to.id:
                return

            if self._running:
                await self._reaction_queue.put(reaction)
            else:
                raise ListenerExit

        # spawn the consumer task first
        self.bot.events.add_temporary_listener("message_reaction_add", consume_reaction)

        # send the stuff we want
        await self.send_current_page()
        await self._add_initial_reactions()

        try:
            while True:
                async with multio.asynclib.timeout_after(120):
                    reaction = await self._reaction_queue.get()

                if reaction.emoji == self.BUTTON_FORWARD:
                    if self.page < len(self._message_chunks) - 1:
                        self.page += 1
                    else:
                        self.page = 0
                    await self.send_current_page()

                if reaction.emoji == self.BUTTON_BACKWARDS:
                    if self.page > 0:
                        self.page -= 1
                    else:
                        self.page = len(self._message_chunks) - 1

                    await self.send_current_page()

                if reaction.emoji == self.BUTTON_STOP:
                    # remove all reactions were done here
                    break

                await self._message.unreact(reaction.emoji, self.respond_to)
        except multio.asynclib.TaskTimeout:
            # eat timeouts but nothing else
            pass

        self._running = False
        # we've broken out of the loop, so remove reactions and cancel the listener
        await self._message.remove_all_reactions()
        self.bot.events.remove_listener_early("message_reaction_add", consume_reaction)
