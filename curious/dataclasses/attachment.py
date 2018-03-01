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
