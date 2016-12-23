from curious import client
from curious.dataclasses.bases import Dataclass


class User(Dataclass):
    """
    This represents a bare user - i.e, somebody without a guild attached.

    This is used in DMs and similar. All members are Users, but no Users are Members.
    """
    def __init__(self, client, **kwargs):
        super().__init__(kwargs.pop("id"), client)

        #: The username of this user.
        self.username = kwargs.pop("username", None)

        #: The discriminator of this user.
        #: Note: This is a string, not an integer.
        self.discriminator = kwargs.pop("discriminator", None)

        #: The avatar hash of this user.
        self._avatar_hash = kwargs.pop("avatar", None)

        #: If this user is verified or not.
        self.verified = kwargs.pop("verified", True)

        #: If this user has MFA enabled or not.
        self.mfa_enabled = kwargs.pop("mfa_enabled", None)

    def _copy(self):
        new_object = object.__new__(self.__class__)
        new_object.id = self.id
        new_object.username = self.username
        new_object.discriminator = self.discriminator
        new_object._avatar_hash = self._avatar_hash
        new_object.verified = self.verified
        new_object.mfa_enabled = self.mfa_enabled

        new_object._bot = self._bot

        return new_object

    @property
    def name(self):
        """
        :return: The computed display name of this user.
            For simplicity sake, this is on User, rather than Member, so it can always be called.
        """
        return getattr(self, "nickname", None) or self.username

    @property
    def mention(self):
        """
        :return: A string that mentions this user.
        """
        nick = getattr(self, "nickname", None)
        if nick:
            return "<@!{}>".format(self.id)

        return "<@{}>".format(self.id)

    @property
    def created_at(self):
        """
        :return: The time this user was created.
        """
        return self.timestamp

    def __str__(self):
        return "{}#{}".format(self.username, self.discriminator)
