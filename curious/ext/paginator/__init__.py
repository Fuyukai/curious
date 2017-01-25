"""
A reactions-based paginator.
"""
import typing

from curious.dataclasses.channel import Channel
from curious.dataclasses.user import User
from curious.dataclasses.member import Member
from curious.dataclasses.embed import Embed
from curious.dataclasses.message import Message
from curious.dataclasses.reaction import Reaction


class ReactionsPaginator(object):
    """
    A paginator for a message using reactions.
    """
    BUTTON_BACKWARDS = "◀"
    BUTTON_FORWARD   = "▶"
    BUTTON_STOP      = "⏹"

    def __init__(self, content: typing.Union[str, typing.List[str]], channel: Channel, respond_to: User,
                 break_at: int=2000):
        """
        :param content: The content to page through.
        :param channel: The channel to send the content to.
        :param respond_to: The member to respond
        :param break_at: The number of characters to break the message up into.
        """
        self._content = content
        self.channel = channel
        self.respond_to = respond_to

        self.bot = self.channel._bot  # hacky af

        # chunk the message up
        if isinstance(content, list):
            self._message_chunks = content
        else:
            self._message_chunks = [self._content[i:i + break_at] for i in range(0, len(self._content), break_at)]

        #: The current page this paginator is on.
        self.page = 0

        #: The message object that is being edited.
        self._message = None  # type: Message

    @classmethod
    async def paginate_response(cls, content: str, responding_to: Message, break_at: int=2000) -> 'ReactionsPaginator':
        """
        Paginates a response to a message.

        :param content: The content to paginate.
        :param responding_to: The message object that you are responding to.
        """
        obb = cls(content, responding_to.channel, responding_to.author)
        await obb.paginate()
        return obb

    async def send_current_page(self):
        """
        Sends the current page to the channel.
        """
        embed = Embed(description=self._message_chunks[self.page])
        embed.set_footer(text="Page {}/{}".format(self.page + 1, len(self._message_chunks)))

        if self._message is None:
            self._message = await self.channel.send(embed=embed)
        else:
            await self._message.edit(embed=embed)

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

        This will continuously listen for reactions on this message until the STOP button is pressed.
        """
        await self.send_current_page()
        await self._add_initial_reactions()

        def predicate(message: Message, author: Member, reaction: Reaction):
            """
            Inner predicate used in `wait_for`.
            """
            if message.id != self._message.id:
                return False

            if author.id != self.respond_to.id:
                return False

            return True

        # Enter the loop.
        while True:
            *_, reaction = await self.bot.wait_for("message_reaction_add", predicate=predicate)
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
                await self._message.remove_all_reactions()
                break

            await self._message.unreact(reaction.emoji, self.respond_to)
