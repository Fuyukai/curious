from curious.dataclasses.bases import IDObject, Dataclass
from curious.dataclasses import user as dt_user
from curious.dataclasses import guild as dt_guild
from curious.dataclasses import channel as dt_channel


class Webhook(Dataclass):
    """
    Represents a webhook member on the server.
    """

    def __init__(self, client, **kwargs):
        # Use the webhook ID is provided (i.e created from a message object).
        # If that doesn't exist, we use the ID of the data instead (it's probably right!).
        super().__init__(kwargs.pop("webhook_id", kwargs.get("id")), client=client)

        #: The user object associated with this webhook.
        self.user = None  # type: dt_user.User

        #: The guild object associated with this webhook.
        self.guild = None  # type: dt_guild.Guild

        #: The channel object associated with this webhook.
        self.channel = None  # type: dt_channel.Channel

        #: The token associated with this webhook.
        #: This is None if the webhook was received from a Message object.
        self.token = kwargs.get("token", None)  # type: str

        #: The default name of this webhook.
        self._default_name = None  # type: str

        #: The default avatar of this webhook.
        self._default_avatar = None  # type: str

    def __repr__(self):
        return "<Webhook id={} name={} channel={}>".format(self.id, self.name, self.channel)

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
