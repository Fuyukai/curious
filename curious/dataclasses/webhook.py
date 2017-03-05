"""
Wrappers for Webhook objects.

.. currentmodule:: curious.dataclasses.webhook
"""

import typing

from curious.dataclasses.bases import IDObject, Dataclass
from curious.dataclasses import user as dt_user
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel
from curious.dataclasses import embed as dt_embed
from curious.util import base64ify


class Webhook(Dataclass):
    """
    Represents a webhook on the guild.
    Messages in a guild can be sent by either a Member or a Webhook object - curious makes a key distinction between 
    them. These classes are *mostly* compatible and don't require much effort to use them generically.
    
    .. code-block:: python
    
        @event("message_create")
        async def handle_messages(ctx, message: Message):
            author = message.author  # can be Webhook or Member

    :ivar id: The ID of the webhook.
    """

    __slots__ = "user", "guild", "channel", "token", "owner", "_default_name", "_default_avatar"

    def __init__(self, client, **kwargs):
        # Use the webhook ID is provided (i.e created from a message object).
        # If that doesn't exist, we use the ID of the data instead (it's probably right!).
        super().__init__(kwargs.get("webhook_id", kwargs.get("id")), cl=client)

        #: The user object associated with this webhook.
        self.user = None  # type: dt_user.User

        #: The guild object associated with this webhook.
        self.guild = None  # type: dt_guild.Guild

        #: The channel object associated with this webhook.
        self.channel = None  # type: dt_channel.Channel

        #: The token associated with this webhook.
        #: This is None if the webhook was received from a Message object.
        self.token = kwargs.get("token", None)  # type: str

        #: The owner of this webhook.
        self.owner = None  # type: dt_user.User

        #: The default name of this webhook.
        self._default_name = None  # type: str

        #: The default avatar of this webhook.
        self._default_avatar = None  # type: str

    def __repr__(self):
        return "<Webhook id={} name={} channel={} owner={}>".format(self.id, self.name,
                                                                    repr(self.channel), repr(self.owner))

    __str__ = __repr__

    @property
    def default_name(self):
        """
        :return: The default name of this webhook.
        """
        return self._default_name

    @property
    def default_avatar_url(self):
        """
        :return: The default avatar URL for this webhook.
        """
        return "https://cdn.discordapp.com/avatars/{}/{}.png".format(self.id, self._default_avatar)

    @property
    def avatar_url(self):
        """
        :return: The computed avatar URL for this webhook.
        """
        if self.user._avatar_hash is None:
            return self.default_avatar_url
        return self.user.avatar_url

    @property
    def name(self):
        """
        :return: The computed name for this webhook.
        """
        # this is kept so you can easily do `message.author.name` all the time.
        return self.user.name or self.default_name

    @classmethod
    def create(cls, channel: 'dt_channel.Channel', *,
               name: str, avatar: bytes) -> 'typing.Awaitable[Webhook]':
        """
        Creates a new webhook.

        :param channel: The :class:`~.Channel` to create the webhook in.
        :param name: The name of the webhook to create.
        :param avatar: The bytes data for the webhook's default avatar.
        :return: A new :class:`~.Webhook`.
        """
        return channel.create_webhook(name=name, avatar=avatar)

    async def get_token(self):
        """
        Gets the token for this webhook, if no token was set earlier.
        :return: The token for the webhook.
        """
        if self.token:
            return self.token

        us = await self._bot.http.get_webhook(self.id)
        self.token = us.get("token")
        return self.token

    async def delete(self):
        """
        Deletes the webhook.

        You must either be the owner of this webhook, or the webhook must have a token associated to delete it.
        """
        if self.token is not None:
            return await self._bot.http.delete_webhook_with_token(self.id, self.token)
        else:
            return await self.guild.delete_webhook(self)

    async def edit(self, *,
                   name: str = None, avatar: bytes = None):
        """
        Edits this webhook.

        :param name: The new name for this webhook.
        :param avatar: The bytes-encoded content of the new avatar.
        :return: The webhook object.
        """
        if avatar is not None:
            avatar = base64ify(avatar)

        if self.token is not None:
            # edit with token, don't pass to guild
            data = await self._bot.http.edit_webhook_with_token(self.id, name=name, avatar=avatar)
            self._default_name = data.get("name")
            self._default_avatar = data.get("avatar")

            # Update the user too
            self.user.username = data.get("name")
            self.user._avatar_hash = data.get("avatar")
        else:
            await self.channel.edit_webhook(self, name=name, avatar=avatar)

        return self

    async def execute(self, *,
                      content: str = None, username: str = None, avatar_url: str = None,
                      embeds: 'typing.List[dt_embed.Embed]'=None, wait: bool = False) -> typing.Union[None, str]:
        """
        Executes the webhook.

        :param content: Any raw content to send.
        :param username: A username to override the default username of the webhook with.
        :param avatar_url: The URL for the avatar to override the default avatar with.
        :param embeds: A list of embeds to add to the message.
        :param wait: Should we wait for the message to arrive before returning?
        """
        if embeds:
            embeds = [embed.to_dict() for embed in embeds]

        if self.token is None:
            await self.get_token()

        data = await self._bot.http.execute_webhook(self.id, self.token,
                                                    content=content, embeds=embeds,
                                                    username=username, avatar_url=avatar_url,
                                                    wait=wait)

        if wait:
            return self._bot.state.make_message(data, cache=False)
