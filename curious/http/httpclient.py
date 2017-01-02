"""
Curious' HTTP client is a thin wrapper over the `requests` library, running in threads.

This is because there is (currently) no native curio HTTP library.
"""
import functools
import logging
import sys
import time
import typing
import weakref
from math import ceil

import curio

import curious
from curious.exc import Forbidden, HTTPException, NotFound, Unauthorized
from curious.http.curio_http import ClientSession, Response


# HTTP exceptions, used to raise errors.


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

                # Close the response.
                await response.close()

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
        return data["url"], data["shards"]

    async def get_application_info(self):
        """
        :return: The application info for this bot.
        """
        url = self.API_BASE + "/oauth2/applications/@me"

        data = await self.get(url, "oauth2:me")
        return data

    async def get_user(self, user_id: int):
        """
        Gets a user from a user ID.

        :param user_id: The ID of the user to fetch.
        :return: A user dictionary.
        """
        url = (self.API_BASE + "/users/{user_id}").format(user_id=user_id)

        data = await self.get(url, bucket="user:get")  # user_id isn't a major param, so handle under one bucket
        return data

    async def send_message(self, channel_id: int, content: str, tts: bool = False, embed: dict=None):
        """
        Sends a message to a channel.

        :param channel_id: The ID of the channel to send to.
        :param content: The content of the message.
        :param tts: Is this message a text to speech message?
        """
        url = (self.CHANNEL_BASE + "/messages").format(channel_id=channel_id)
        params = {
            "tts": tts,
        }

        if content is not None:
            params["content"] = content

        if embed is not None:
            params["embed"] = embed

        data = await self.post(url, "messages:{}".format(channel_id), json=params)
        return data

    async def upload_file(self, channel_id: int, file_content: bytes, *,
                          filename: str=None, content: str=None):
        """
        Uploads a file to the current channel.

        This will encode the data as multipart/form-data.

        :param channel_id: The channel ID to upload to.
        :param file_content: The content of the file being uploaded.
        :param filename: The filename of the file being uploaded.
        :param content: Any optional message content to send with this file.
        """
        url = (self.CHANNEL_BASE + "/messages").format(channel_id=channel_id)
        payload = {}
        if content is not None:
            payload["content"] = content

        files = {
            "file": {
                "filename": filename,
                "content": file_content
            }
        }
        data = await self.post(url, "messages:{}".format(channel_id),
                               body=payload, files=files)
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
        :param new_content: The new content of the message.
        :return: The new Message object.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}").format(channel_id=channel_id, message_id=message_id)
        payload = {
            "content": new_content
        }

        data = await self.patch(url, "messages:{}".format(channel_id), json=payload)
        return data

    async def pin_message(self, channel_id: int, message_id: int):
        """
        Pins a message to the channel.

        :param channel_id: The channel ID to pin in.
        :param message_id: The message ID of the message to pin.
        """
        url = (self.CHANNEL_BASE + "/pins/{message_id}").format(channel_id=channel_id, message_id=message_id)

        data = await self.put(url, "pins:{}".format(channel_id), json={})
        return data

    async def unpin_message(self, channel_id: int, message_id: int):
        """
        Unpins a message from the channel.

        :param channel_id: The channel ID to unpin in.
        :param message_id: The message ID of the message to unpin.
        """
        url = (self.CHANNEL_BASE + "/pins/{message_id}").format(channel_id=channel_id, message_id=message_id)

        data = await self.delete(url, "pins:{}".format(channel_id))
        return data

    async def get_message(self, channel_id: int, message_id: int):
        """
        Gets a single message from the channel.

        :param channel_id: The channel ID to get the message from.
        :param message_id: The message ID of the message to get.
        :return: The message data.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}").format(channel_id=channel_id, message_id=message_id)

        data = await self.get(url, "messages:{}".format(channel_id))
        return data

    async def get_messages(self, channel_id: int, *,
                           before: int = None, after: int = None, around: int = None,
                           limit: int = 100):
        """
        Gets a list of messages from a channel.

        This requires READ_MESSAGES on the channel.
        :param channel_id: The channel ID to receive messages from.
        :param before: Get messages before this snowflake.
        :param after: Get messages after this snowflake.
        :param around: Get messages around this snowflake.
        :param limit: The maximum number of messages to return.

        :return: A list of message dictionaries.
        """
        url = (self.CHANNEL_BASE + "/messages").format(channel_id=channel_id)
        payload = {
            "limit": str(limit)
        }

        if before:
            payload["before"] = str(before)

        if after:
            payload["after"] = str(after)

        if around:
            payload["around"] = str(around)

        data = await self.get(url, bucket="messages:{}".format(channel_id), params=payload)
        return data

    async def get_pins(self, channel_id: int):
        """
        Gets the pins for a channel.

        :param channel_id: The channel ID to get pins from.
        """
        url = (self.CHANNEL_BASE + "/pins").format(channel_id=channel_id)

        data = await self.get(url, bucket="pins:{}".format(channel_id))
        return data

    async def bulk_delete_messages(self, channel_id: int, message_ids: typing.List[int]):
        """
        Deletes multiple messages.

        This will silently discard any messages that don't exist.

        This requires MANAGE_MESSAGES on the channel, regardless of what messages are being deleted.

        :param channel_id: The channel ID to delete messages from.
        :param message_ids: A list of messages to delete.
        """
        url = (self.CHANNEL_BASE + "/messages/bulk-delete").format(channel_id=channel_id)
        payload = {
            "messages": [str(message_id) for message_id in message_ids]
        }

        data = await self.post(url, bucket="messages:bulk_delete:{}".format(channel_id), json=payload)
        return data

    # Profile endpoints
    async def edit_profile(self, username: str = None, avatar: str = None):
        """
        Edits the profile of the bot.

        :param username: The new username of the bot, or None if it is not to be changed.
        :param avatar: The new avatar of the bot, or None if it not to be changed.
        """
        url = self.USER_ME
        payload = {}
        if username:
            payload["username"] = username

        if avatar:
            payload["avatar"] = avatar

        data = await self.patch(url, bucket="users:edit", json=payload)
        return data

    # Moderation
    async def kick_member(self, guild_id: int, member_id: int):
        """
        Kicks a member from a guild.

        :param guild_id: The guild ID to kick in.
        :param member_id: The member ID to kick from the guild.
        """
        url = (self.GUILD_BASE + "/members/{member_id}").format(guild_id=guild_id, member_id=member_id)

        data = await self.delete(url, bucket="members:{}".format(guild_id))
        return data

    async def get_bans(self, guild_id: int):
        """
        Gets a list of bans from a guild.

        :param guild_id: The guild to get bans from.
        :return: A list of user dicts containing ban information.
        """
        url = (self.GUILD_BASE + "/bans").format(guild_id=guild_id)

        data = await self.get(url, bucket="bans:{}".format(guild_id))
        return data

    async def ban_user(self, guild_id: int, user_id: int,
                       delete_message_days: int = 7):
        """
        Bans a user from a guild.

        :param guild_id: The ID of the guild to ban on.
        :param user_id: The user ID to ban from the guild.
        :param delete_message_days: The number of days to delete messages from this user.
        """
        url = (self.GUILD_BASE + "/bans/{user_id}").format(guild_id=guild_id, user_id=user_id)
        payload = {}

        if delete_message_days:
            payload["delete-message-days"] = delete_message_days

        data = await self.put(url, bucket="bans:{}".format(guild_id), json=payload)
        return data

    async def unban_user(self, guild_id: int, user_id: int):
        """
        Unbans a user from a guild.

        :param guild_id: The ID of the guild to unban on.
        :param user_id: The user ID that has been forgiven.
        """
        url = (self.GUILD_BASE + "/bans/{user_id}").format(guild_id=guild_id, user_id=user_id)

        data = await self.delete(url, bucket="bans:{}".format(guild_id))
        return data

    async def add_single_role(self, guild_id: int, member_id: int, role_id: int):
        """
        Adds a single role to a member.

        If you want to add multiple roles to a member, use :meth:`add_roles`.

        :param guild_id: The guild ID that contains the objects.
        :param member_id: The member ID to add the role to.
        :param role_id: The role ID to add to the member.
        """
        url = (self.GUILD_BASE + "/members/{member_id}/roles/{role_id}").format(guild_id=guild_id, member_id=member_id,
                                                                                role_id=role_id)

        data = await self.put(url, bucket="roles:{}".format(guild_id))
        return data

    async def modify_member_roles(self, guild_id: int, member_id: int, role_ids: typing.Iterable[int]):
        """
        Modifies the roles that a member object contains.

        :param guild_id: The guild ID that contains the objects.
        :param member_id: The member ID to add the role to.
        :param role_ids: The role IDs to add to the member.
        """
        url = (self.GUILD_BASE + "/members/{member_id}").format(guild_id=guild_id, member_id=member_id)
        payload = {
            "roles": [str(id) for id in role_ids]
        }

        data = await self.patch(url, bucket="roles:{}".format(guild_id), json=payload)
        return data

    async def modify_overwrite(self, channel_id: int, target_id: int, type_: str,
                               *, allow: int=0, deny: int=0):
        """
        Modifies or adds an overwrite.

        :param channel_id: The channel ID to edit.
        :param target_id: The target of the override.
        :param type_: The type the target is.

        :param allow: The permission bitfield of permissions to allow.
        :param deny: The permission bitfield of permissions to deny.
        """
        url = (self.CHANNEL_BASE + "/permissions/{target_id}").format(channel_id=channel_id, target_id=target_id)
        payload = {
            "allow": allow,
            "deny": deny,
            "type": type_
        }

        data = await self.put(url, bucket="channels:permissions:{}".format(channel_id), json=payload)
        return data

    async def remove_overwrite(self, channel_id: int, target_id: int):
        """
        Removes an overwrite.

        :param channel_id: The channel ID to edit.
        :param target_id: The target of the override.
        """
        url = (self.CHANNEL_BASE + "/permissions/{target_id}".format(channel_id=channel_id, target_id=target_id))

        data = await self.delete(url, bucket="channels:permissions:{}".format(channel_id))
        return data

    # Misc
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
