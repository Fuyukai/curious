from curious.dataclasses.bases import Dataclass


class Attachment(Dataclass):
    """
    Represents an attachment.
    """
    def __init__(self, id: int, bot, **kwargs):
        super().__init__(id, cl=bot)

        #: The filename for this attachment.
        self.filename: str = kwargs.get("filename")

        #: The size of this attachment (in bytes).
        self.size: int = kwargs.get("size")

        #: The URL of this attachment.
        self.url: str = kwargs.get("url")

        #: The proxy_url of this attachment.
        self.proxy_url: str = kwargs.get("proxy_url")

        #: The height of this attachment, if an image.
        self.height: int = kwargs.get("height")

        #: The width of this attachment, if an image.
        self.width: int = kwargs.get("width")

    async def download(self) -> bytes:
        """
        Downloads the attachment into bytes.
        """
        bucket = ("attachment", self.id)
        data = await self._bot.http.request(bucket, method="GET", uri=self.proxy_url)
        return data
