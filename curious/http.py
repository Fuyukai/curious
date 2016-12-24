"""
Curious' HTTP client is a thin wrapper over the `requests` library, running in threads.

This is because there is (currently) no native curio HTTP library.
"""
import functools

import collections
import json
import typing
import weakref
import logging
import curio
import sys
import time
from math import ceil

import curious
from curious.curio_http import ClientSession, Response


# HTTP exceptions, used to raise errors.
class HTTPException(Exception):
    """
    Raised when a HTTP request fails with a 400 <= e < 600 error code.
    """

    def __init__(self, response: Response, error: dict):
        self.response = response
        self.error = error

    def __repr__(self):
        return repr(self.error)

    def __str__(self):
        return str(self.error)


class Unauthorized(HTTPException):
    """
    Raised when your bot token is invalid.
    """


class Forbidden(HTTPException):
    """
    Raised when you don't have permission for something.
    """


class NotFound(HTTPException):
    """
    Raised when something could not be found.
    """


class HTTPClient(object):
    API_BASE = "https://discordapp.com/api/v6"
    GUILD_BASE = API_BASE + "/guilds/{guild_id}"
    CHANNEL_BASE = API_BASE + "/channels/{channel_id}"

    USER_ME = API_BASE + "/users/@me"

    def __init__(self, token: str):
        #: The token used for all requests.
        self.token = token

        # Calculated headers
        headers = {
            "Authorization": "Bot {}".format(self.token),
            "User-Agent": "DiscordBot (https://github.com/SunDwarf/curious {0}) Python/{1[0]}.{1[1]}"
                          " curio/{2}".format(curious.__version__, sys.version_info,
                                              curio.__version__)
        }

        self.session = ClientSession()
        self.session.headers = headers

        #: Ratelimit buckets.
        self._rate_limits = weakref.WeakValueDictionary()

        #: Ratelimit remaining times
        self._ratelimit_remaining = {}

        self.logger = logging.getLogger("curious.http")

    def get_ratelimit_lock(self, bucket: object):
        """
        Gets a ratelimit lock from the dict if it exists, otherwise creates a new one.
        """
        try:
            return self._rate_limits[bucket]
        except KeyError:
            lock = curio.Lock()
            self._rate_limits[bucket] = lock
            return lock

    # Special wrapper functions

    async def __perform_request(self, *args, **kwargs) -> Response:
        """
        A wrapper for requests' request that uses curio.abide().

        This only performs the request - it does NOT do any ratelimiting.
        Hence, this method is unsafe, and is private. It should not be used by client code.
        """
        partial = functools.partial(self.session.request, *args, **kwargs)
        coro = curio.timeout_after(5, curio.abide(partial))
        return await coro

    async def get_response_data(self, response: Response) -> typing.Union[str, dict]:
        """
        Return either the text of a request or the JSON.

        :param response: The response to use.
        """
        if response.headers.get("Content-Type", None) == "application/json":
            return await response.json()

        return await response.text()

    async def request(self, bucket: object, *args, **kwargs):
        """
        Makes a rate-limited request.

        This will respect Discord's X-Ratelimit-Limit headers to make requests.

        :param bucket: The bucket this request falls under.
        """
        # Okay, an English explaination of how this works.
        # First, it loads the curio-based lock from the defaultdict of lock, keyed by bucket.
        # Then, it tries to acquire the lock. This is held by one request at a time, naturally.

        # Normally, the lock is immediately released upon a request finishing, which allows the next request to
        # handle it. However, once X-Ratelimit-Remaining is 0, we don't want any more requests to be made until the
        # time limit is over. So the request sleeps for (X-RateLimit-Reset - time.time()) seconds, then unlocks the
        # lock.

        lock = self.get_ratelimit_lock(bucket)
        try:
            await lock.acquire()

            if bucket in self._ratelimit_remaining:
                # Make sure we have enough tries left.
                tries, reset_time = self._ratelimit_remaining[bucket]

                if tries <= 0:
                    # We need to sleep for a bit before we can start making another request.
                    sleep_time = ceil(reset_time - time.time())
                    self.logger.debug("Sleeping with lock open for {} seconds.".format(sleep_time))
                    await curio.sleep(sleep_time)

            for tries in range(0, 5):
                # Make the request.
                response = await self.session.request(*args, **kwargs)
                self.logger.debug("{} {} => {}".format(kwargs.get("method", "???"),
                                                       kwargs.get("url", "???"),
                                                       response.status_code))

                if response.status_code == 502:
                    # 502 means that we can retry without worrying about ratelimits.
                    # Perform exponential backoff to prevent spamming discord.
                    sleep_time = 1 + (tries * 2)
                    await curio.sleep(sleep_time)
                    continue

                if response.status_code == 429:
                    # This is bad!
                    # But it's okay, we can handle it.
                    self.logger.warning("Hit a 429 in bucket {}. Check your clock!".format(bucket))
                    sleep_time = ceil(int(response.headers["Retry-After"]) / 1000)
                    await curio.sleep(sleep_time)
                    continue

                # Extract ratelimit headers.
                remaining = int(response.headers.get("X-Ratelimit-Remaining", 1))
                reset = int(response.headers.get("X-Ratelimit-Reset", 1))

                # Update the ratelimit headers.
                self._ratelimit_remaining[bucket] = remaining, reset

                # Next, check if we need to sleep.
                # Check if we need to sleep.
                # This is signaled by Ratelimit-Remaining being 0 or Ratelimit-Global being True.
                should_sleep = remaining == 0 or \
                               response.headers.get("X-Ratelimit-Global") == "true"

                if should_sleep:
                    # The time until the reset is given by X-Ratelimit-Reset.
                    # Failing that, it's also given by the Retry-After header, which is in ms.
                    reset = response.headers.get("X-Ratelimit-Reset")
                    if reset:
                        sleep_time = int(reset) - time.time()
                    else:
                        sleep_time = ceil(int(response.headers.get("Retry-After")) / 1000)

                    self.logger.debug("Being ratelimited under bucket {}, waking in {} seconds".format(bucket,
                                                                                                       sleep_time))

                    # Sleep that amount of time.
                    await curio.sleep(sleep_time)

                # Now, we have that nuisance out of the way, we can try and get the result from the request.
                result = await self.get_response_data(response)

                # Status codes between 200 and 300 mean success, so we return the data directly.
                if 200 <= response.status_code < 300:
                    return result

                # Status codes between 400 and 600 are BAD!
                # So we raise an exception.
                # However, special case 404 and 403, because they're Unique Exceptions(tm).
                if 400 <= response.status_code < 600:
                    if response.status_code == 401:
                        raise Unauthorized(response, result)

                    if response.status_code == 403:
                        raise Forbidden(response, result)

                    if response.status_code == 404:
                        raise NotFound(response, result)

                    raise HTTPException(response, result)

        finally:
            await lock.release()

    async def get(self, url: str, bucket: str,
                  *args, **kwargs):
        return await self.request(("GET", bucket), method="GET", url=url, *args, **kwargs)

    async def post(self, url: str, bucket: str,
                   *args, **kwargs):
        return await self.request(("POST", bucket), method="POST", url=url, *args, **kwargs)

    async def put(self, url: str, bucket: str,
                  *args, **kwargs):
        return await self.request(("PUT", bucket), method="PUT", url=url, *args, **kwargs)

    async def delete(self, url: str, bucket: str,
                     *args, **kwargs):
        return await self.request(("DELETE", bucket), method="DELETE", url=url, *args, **kwargs)

    async def patch(self, url: str, bucket: str,
                    *args, **kwargs):
        return await self.request(("PATCH", bucket), method="PATCH", url=url, *args, **kwargs)

    # Non-generic methods
    async def get_gateway_url(self):
        """
        :return: The websocket gateway URL to get.
        """
        # Use /gateway/bot here to ensure our token is valid.
        url = self.API_BASE + "/gateway/bot"
        data = await self.get(url, "gateway")

        return data["url"]

    async def get_shard_count(self):
        """
        :return: The recommended number of shards for this bot.
        """
        url = self.API_BASE + "/gateway/bot"
        data = await self.get(url, "gateway")

        return data["shards"]

    async def get_application_info(self):
        """
        :return: The application info for this bot.
        """
        url = self.API_BASE + "/oauth2/applications/@me"
        data = await self.get(url, "oauth2:me")

        return data

    async def send_message(self, channel_id: int, content: str, tts: bool=False):
        """
        Sends a message to a channel.

        :param channel_id: The ID of the channel to send to.
        :param content: The content of the message.
        :param tts: Is this message a text to speech message?
        """
        url = (self.CHANNEL_BASE + "/messages").format(channel_id=channel_id)
        params = {
            "content": content,
            "tts": tts,
        }

        data = await self.post(url, "messages:{}".format(channel_id), json=params)
        return data

    async def delete_message(self, channel_id: int, message_id: int):
        """
        Deletes a message.

        This requires the MANAGE_MESSAGES permission.

        :param channel_id: The channel ID that the message is in.
        :param message_id: The message ID of the message.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}").format(channel_id=channel_id, message_id=message_id)

        data = await self.delete(url, "messages:{}".format(channel_id))
        return data

    async def edit_message(self, channel_id: int, message_id: int, new_content: str):
        """
        Edits a message.

        This will only work on your own messages.

        :param channel_id: The channel ID that the message is in.
        :param message_id: The message ID of the message.
        :return: The new Message object.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}").format(channel_id=channel_id, message_id=message_id)
        payload = {
            "content": new_content
        }

        data = await self.patch(url, "messages:{}".format(channel_id), json=payload)
        return data

    async def open_private_channel(self, user_id: int):
        """
        Opens a new private channel with a user.

        :param user_id: The user ID of the user to open with.
        """
        url = self.USER_ME + "/channels"
        params = {
            "recipient_id": user_id
        }

        data = await self.post(url, "channels:private:create", json=params)
        return data

    async def leave_guild(self, guild_id: str):
        """
        Leaves a guild.

        :param guild_id: The guild ID of the guild to leave.
        """
        url = self.USER_ME + "/guilds/{}".format(guild_id)

        data = await self.delete(url, "guild:leave")
        return data
