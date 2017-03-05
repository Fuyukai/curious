"""
Wrappers for Embed objects.

.. currentmodule:: curious.dataclasses.embed
"""

import datetime

from curious.util import attrdict


def _(s, n, v): raise KeyError(n)


class Attachment(attrdict):
    def __init__(self, **kwargs):
        self.id = int(kwargs.get("id", 0))
        attrdict.__init__(self, **kwargs)

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)


class Embed(object):  # not an IDObject! Embeds don't have IDs.
    """
    Represents an Embed object on Discord.
    """

    def __init__(self, *,
                 title: str = None,
                 description: str = None,
                 colour: int = None,
                 type_: str = None,
                 url: str = None,
                 timestamp: str = None,
                 **kwargs):

        #: The title of this embed.
        self.title = title

        #: The description of this embed.
        self.description = description

        if colour is None:
            # for passing in from discord
            colour = kwargs.get("color")

        #: The colour of this embed.
        self.colour = colour

        #: The type of this embed.
        self.type_ = type_

        #: The URL for this embed.
        self.url = url

        #: The timestamp for this embed.
        self.timestamp = timestamp  # type: datetime.datetime

        #: The fields for this embed.
        self._fields = []

        #: The footer for this embed.
        self.footer = attrdict(**kwargs.get("footer", {}))

        #: The author of this embed.
        self.author = attrdict(**kwargs.get("author", {}))

        #: The image for this embed.
        self.image = attrdict(**kwargs.get("image", {}))

        #: The video for this embed.
        self.video = attrdict(**kwargs.get("video", {}))

        #: The thumbnail for this embed.
        self.thumbnail = attrdict(**kwargs.get("thumbnail", {}))

    def add_field(self, *, name: str, value: str,
                  inline: bool = True) -> 'Embed':
        """
        Adds a field to the embed.

        :param name: The field name.
        :param value: The field value.
        :param inline: Is this field inline?
        :return: The Embed object.
        """
        if isinstance(name, str) and len(name) == 0:
            raise ValueError("Name must not be empty")

        if isinstance(value, str) and len(value) == 0:
            raise ValueError("Value must not be empty")

        self._fields.append(attrdict({"name": name, "value": value, "inline": inline}))
        return self

    def set_author(self, *, name: str = None, url: str = None) -> 'Embed':
        """
        Sets the author of this embed.

        :param name: The name of the author.
        :param url: The URL of the author.
        :return: The Embed object.
        """

        self.author = attrdict()
        if name:
            self.author.name = name

        if url:
            self.author.url = url

        return self

    def set_footer(self, *, text: str = None, icon_url: str = None) -> 'Embed':
        """
        Sets the footer of this embed.

        :param text: The footer text of this embed.
        :param icon_url: The icon URL for the footer.
        :return: The Embed object.
        """
        self.footer = attrdict()
        if text:
            self.footer.text = text

        if icon_url:
            self.footer.icon_url = icon_url

    def set_image(self, *, image_url: str) -> 'Embed':
        """
        Sets the image of this embed.

        :param image_url: The image URL of this embed.
        :return: The Embed object.
        """
        self.image = attrdict()

        if not image_url.startswith("http") or image_url.startswith("attachment://"):
            raise ValueError("Image URLs must start with http[s]")

        if image_url:
            self.image.image_url = image_url

        return self

    def to_dict(self):
        """
        Converts this embed into a flattened dict.
        """
        payload = {
            "type": self.type_ if self.type_ else "rich"
        }

        if self.title:
            payload["title"] = self.title

        if self.description:
            payload["description"] = self.description

        if self.url:
            payload["url"] = self.url

        if self.colour:
            payload["color"] = self.colour  # american spelling

        if self.timestamp:
            payload["timestamp"] = self.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")

        # attrdicts can be automatically json dumped easily
        # so we just go and shove these right in there
        if self.footer:
            payload["footer"] = self.footer

        if self.thumbnail:
            payload["thumbnail"] = self.thumbnail

        if self.image:
            payload["image"] = self.image

        if self.author:
            payload["author"] = self.author

        payload["fields"] = self._fields

        return payload
