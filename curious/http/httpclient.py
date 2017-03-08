"""
The main Discord HTTP interface.
"""
import datetime
import logging
import sys
import time
import typing
import warnings
import weakref
from email.utils import parsedate
from math import ceil

# try and load a C impl of LRU first
try:
    from lru import LRU as c_lru


    def _make_lru_dict(size):
        return c_lru(size)

except ImportError:
    # fall back to a pure-python (the default) version
    from pylru import lrucache as py_lru

    warnings.warn("Using pure-python `pylru` library over `lru-dict` faster C library!")


    def _make_lru_dict(size):
        return py_lru(size)

import curio

import curious
from curious.exc import Forbidden, HTTPException, NotFound, Unauthorized
from curious.http.curio_http import ClientSession, Response


def parse_date_header(header: str) -> datetime.datetime:
    """
    Parses a date header.

    :param header: The contents of the header to parse.
    :return: A :class:`datetime.datetime` that corresponds to the date header.
    """
    return datetime.datetime(*parsedate(header)[:6])


class HTTPClient(object):
    """
    The HTTP client object used to make requests to Discord's servers.

    If a particular method is not listed here, you can use one of the five following methods to make a manual request:

        - :meth:`HTTPClient.get`
        - :meth:`HTTPClient.post`
        - :meth:`HTTPClient.put`
        - :meth:`HTTPClient.delete`
        - :meth:`HTTPClient.patch`

    All of these functions require a **ratelimit bucket** which will be used to prevent the client from hitting 429
    ratelimits.
    """
    API_BASE = "https://discordapp.com/api/v6"
    GUILD_BASE = API_BASE + "/guilds/{guild_id}"
    CHANNEL_BASE = API_BASE + "/channels/{channel_id}"

    USER_ME = API_BASE + "/users/@me"

    def __init__(self, token: str, *,
                 bot: bool = True):
        #: The token used for all requests.
        self.token = token

        # Calculated headers
        headers = {
            "User-Agent": "DiscordBot (https://github.com/SunDwarf/curious {0}) Python/{1[0]}.{1[1]}"
                          " curio/{2}".format(curious.__version__, sys.version_info,
                                              curio.__version__)
        }

        if bot:
            headers["Authorization"] = "Bot {}".format(self.token)
        else:
            headers["Authorization"] = self.token

        self.session = ClientSession()
        self.session.headers = headers

        #: Ratelimit buckets.
        self._rate_limits = weakref.WeakValueDictionary()

        #: Ratelimit remaining times
        self._ratelimit_remaining = _make_lru_dict(1024)

        # Global ratelimit lock
        self.global_lock = curio.Lock()

        self._is_bot = bot

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
        # If we're being globally ratelimited, this will block until the global lock is finished.
        await self.global_lock.acquire()
        # Immediately release it because we're no longer being globally ratelimited.
        await self.global_lock.release()
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

                if response.status_code in [500, 502]:
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
                               response.headers.get("X-Ratelimit-Global", None) is not None
                is_global = response.headers.get("X-Ratelimit-Global", None) is not None

                if should_sleep:
                    # The time until the reset is given by X-Ratelimit-Reset.
                    # Failing that, it's also given by the Retry-After header, which is in ms.
                    reset = response.headers.get("X-Ratelimit-Reset")
                    # Parse Discord's Date header to use their time rather than local time.
                    parsed_time = parse_date_header(response.headers.get("Date")).timestamp()
                    if reset:
                        sleep_time = int(reset) - parsed_time
                    else:
                        sleep_time = ceil(int(response.headers.get("Retry-After")) / 1000)

                    if is_global:
                        self.logger.debug("Reached the global ratelimit, acquiring global lock.")
                        await self.global_lock.acquire()
                    else:
                        self.logger.debug("Being ratelimited under bucket {}, waking in {} seconds".format(bucket,
                                                                                                           sleep_time))
                    # Sleep that amount of time.
                    await curio.sleep(sleep_time)
                    # If the global lock is acquired, unlock it now
                    if is_global:
                        await self.global_lock.release()

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
            # Only release the global lock if we need to
            if self.global_lock.locked():
                await self.global_lock.release()

    async def get(self, url: str, bucket: str,
                  *args, **kwargs):
        """
        Makes a GET request.

        :param url: The URL to request.
        :param bucket: The ratelimit bucket to file this request under.
        """
        return await self.request(("GET", bucket), method="GET", url=url, *args, **kwargs)

    async def post(self, url: str, bucket: str,
                   *args, **kwargs):
        """
        Makes a POST request.

        :param url: The URL to request.
        :param bucket: The ratelimit bucket to file this request under.
        """
        return await self.request(("POST", bucket), method="POST", url=url, *args, **kwargs)

    async def put(self, url: str, bucket: str,
                  *args, **kwargs):
        """
        Makes a PUT request.

        :param url: The URL to request.
        :param bucket: The ratelimit bucket to file this request under.
        """
        return await self.request(("PUT", bucket), method="PUT", url=url, *args, **kwargs)

    async def delete(self, url: str, bucket: str,
                     *args, **kwargs):
        """
        Makes a DELETE request.

        :param url: The URL to request.
        :param bucket: The ratelimit bucket to file this request under.
        """
        return await self.request(("DELETE", bucket), method="DELETE", url=url, *args, **kwargs)

    async def patch(self, url: str, bucket: str,
                    *args, **kwargs):
        """
        Makes a PATCH request.

        :param url: The URL to request.
        :param bucket: The ratelimit bucket to file this request under.
        """
        return await self.request(("PATCH", bucket), method="PATCH", url=url, *args, **kwargs)

    # Non-generic methods
    async def get_gateway_url(self):
        """
        It is not recommended to use this method - use :meth:`HTTPClient.get_shard_count` instead. That method
        provides the gateway URL as well.

        :return: The websocket gateway URL to get.
        """
        url = self.API_BASE + "/gateway"

        data = await self.get(url, "gateway")
        return data["url"]

    async def get_shard_count(self):
        """
        :return: The recommended number of shards for this bot.
        """
        if not self._is_bot:
            raise Forbidden(None, {"code": 20002, "message": "Only bots can use this endpoint"})

        url = self.API_BASE + "/gateway/bot"

        data = await self.get(url, "gateway")
        return data["url"], data["shards"]

    async def get_user_me(self):
        """
        Gets the current user.
        """
        url = self.USER_ME

        data = await self.get(url, bucket="user:get")
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

    async def get_guild(self, guild_id: int):
        """
        Gets a guild by guild ID.

        :param guild_id: The ID of the guild to get.
        :return: A guild object.
        """
        url = self.GUILD_BASE.format(guild_id=guild_id)

        data = await self.get(url, bucket="guild:{}".format(guild_id))
        return data

    async def get_guild_channels(self, guild_id: int):
        """
        Gets a list of channels in a guild.

        :param guild_id: The ID of the guild to get.
        :return: A list of channel objects.
        """
        url = (self.GUILD_BASE + "/channels").format(guild_id=guild_id)

        data = await self.get(url, bucket="guild:{}".format(guild_id))
        return data

    async def get_guild_members(self, guild_id: int, *,
                                limit: int = None, after: int = None):
        """
        Gets guild members for the specified guild.

        :param guild_id: The ID of the guild to get.
        :param limit: The maximum number of members to get.
        :param after: The ID to fetch members after.
        """
        url = (self.GUILD_BASE + "/members").format(guild_id=guild_id)
        params = {}

        if limit is not None:
            params["limit"] = limit

        if after is not None:
            params["after"] = after

        data = await self.get(url, bucket="guild:{}".format(guild_id), params=params)
        return data

    async def get_guild_member(self, guild_id: int, member_id: int):
        """
        Gets a guild member.

        :param guild_id: The guild ID to get.
        :param member_id: The member ID to get.
        """
        url = (self.GUILD_BASE + "/members/{member_id}").format(guild_id=guild_id, member_id=member_id)

        data = await self.get(url, bucket="guild:{}".format(guild_id))
        return data

    async def get_channel(self, channel_id: int):
        """
        Gets a channel.

        :param channel_id: The channel ID to get.
        """
        url = self.CHANNEL_BASE.format(channel_id=channel_id)

        data = await self.get(url, bucket="channel:{}".format(channel_id))
        return data

    async def send_typing(self, channel_id: str):
        """
        Starts typing in a channel.

        :param channel_id: The ID of the channel to type in.
        """
        url = (self.CHANNEL_BASE + "/typing").format(channel_id=channel_id)

        data = await self.post(url, bucket="typing:{}".format(channel_id))
        return data

    async def send_message(self, channel_id: int, content: str, tts: bool = False, embed: dict = None):
        """
        Sends a message to a channel.

        :param channel_id: The ID of the channel to send to.
        :param content: The content of the message.
        :param tts: Is this message a text to speech message?
        """
        url = (self.CHANNEL_BASE + "/messages").format(channel_id=channel_id)
        payload = {
            "tts": tts,
        }

        if content is not None:
            payload["content"] = content

        if embed is not None:
            payload["embed"] = embed

        data = await self.post(url, "messages:{}".format(channel_id), json=payload)
        return data

    async def upload_file(self, channel_id: int, file_content: bytes, *,
                          filename: str = None, content: str = None):
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

    async def edit_message(self, channel_id: int, message_id: int, content: str = None, embed: dict = None):
        """
        Edits a message.

        This will only work on your own messages.

        :param channel_id: The channel ID that the message is in.
        :param message_id: The message ID of the message.
        :param content: The new content of the message.
        :param embed: The new embed of the message.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}").format(channel_id=channel_id, message_id=message_id)
        payload = {}

        if content is not None:
            payload["content"] = content

        if embed is not None:
            payload["embed"] = embed

        data = await self.patch(url, "messages:{}".format(channel_id), json=payload)
        return data

    async def react_to_message(self, channel_id: int, message_id: int, emoji: str):
        """
        Reacts to a message.

        :param channel_id: The channel ID that the message is in.
        :param message_id: The message ID of the message.
        :param emoji: The emoji to react with.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}/reactions/{emoji}/@me").format(channel_id=channel_id,
                                                                                          message_id=message_id,
                                                                                          emoji=emoji)

        data = await self.put(url, "reactions:{}".format(channel_id))
        return data

    async def delete_reaction(self, channel_id: int, message_id: int, emoji: str,
                              victim: int = None):
        """
        Deletes a reaction from a message.

        :param channel_id: The channel ID of the channel containing the message.
        :param message_id: The message ID to remove reactions from.
        :param emoji: The emoji to remove.
        :param victim: The victim to remove. \
            If this is None, our own reaction is removed.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}/reactions/{emoji}/{me}") \
            .format(channel_id=channel_id, message_id=message_id, emoji=emoji,
                    me="@me" if not victim else victim)

        data = await self.delete(url, bucket="reactions:{}".format(channel_id))
        return data

    async def delete_all_reactions(self, channel_id: int, message_id: int):
        """
        Removes all reactions from a message.

        :param channel_id: The channel ID of the channel containing the message.
        :param message_id: The message ID to remove reactions from.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}/reactions").format(channel_id=channel_id,
                                                                              message_id=message_id)

        data = await self.delete(url, bucket="reactions:{}".format(channel_id))
        return data

    async def get_reaction_users(self, channel_id: int, message_id: int, emoji: str):
        """
        Gets a list of users who reacted to this message with the specified reaction.

        :param channel_id: The channel ID to check in.
        :param message_id: The message ID to check.
        :param emoji: The emoji to get reactions for.
        """
        url = (self.CHANNEL_BASE + "/messages/{message_id}/reactions/{emoji}").format(channel_id=channel_id,
                                                                                      message_id=message_id,
                                                                                      emoji=emoji)

        data = await self.get(url, bucket="reactions:{}".format(channel_id))
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
    async def edit_profile(self, username: str = None, avatar: str = None,
                           password: str=None):
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

        if password:
            payload["password"] = password

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

    async def modify_guild(self, guild_id: int, *,
                           name: str = None, icon_content: bytes = None,
                           region: str = None, verification_level: int = None,
                           default_message_notifications: int = None,
                           afk_channel_id: int = None, afk_timeout: int = None,
                           splash_content: bytes = None):
        """
        Modifies a guild.

        See https://discordapp.com/developers/docs/resources/guild#modify-guild for the fields available.
        """
        url = self.GUILD_BASE.format(guild_id=guild_id)
        payload = {}

        if name:
            payload["name"] = name

        if icon_content:
            payload["icon"] = icon_content

        if region:
            payload["region"] = region

        if verification_level is not None:
            payload["verification_level"] = verification_level

        if default_message_notifications is not None:
            payload["default_message_notifications"] = default_message_notifications

        if afk_channel_id == 0:
            payload["afk_channel_id"] = None
        elif afk_channel_id:
            payload["afk_channel_id"] = str(afk_channel_id)

        if afk_timeout:
            payload["afk_timeout"] = afk_timeout

        if splash_content:
            payload["splash"] = splash_content

        data = await self.patch(url, bucket="guild_edit:{}".format(guild_id), json=payload)
        return data

    async def create_role(self, guild_id: int) -> dict:
        """
        Creates a role in a guild.

        :param guild_id: The guild to create the role in.
        """
        url = (self.GUILD_BASE + "/roles").format(guild_id=guild_id)

        data = await self.post(url, bucket="guild_roles:{}".format(guild_id))
        return data

    async def edit_role(self, guild_id: int, role_id: int,
                        name: str = None, permissions: int = None, position: int = None,
                        colour: int = None, hoist: bool = None, mentionable: bool = None):
        """
        Edits a role.

        :param guild_id: The guild ID that contains the role.
        :param role_id: The role ID to edit.
        """
        url = (self.GUILD_BASE + "/roles/{role_id}").format(guild_id=guild_id, role_id=role_id)
        payload = {}

        if name:
            payload["name"] = name

        if permissions is not None:
            payload["permissions"] = permissions

        if position is not None:
            payload["position"] = position

        if colour:
            payload["color"] = colour

        if hoist is not None:
            payload["hoist"] = hoist

        if mentionable is not None:
            payload["mentionable"] = mentionable

        data = await self.patch(url, bucket="guild_roles:{}".format(guild_id), json=payload)
        return data

    async def delete_role(self, guild_id: int, role_id: int):
        """
        Deletes a role.

        :param guild_id: The guild ID that contains the role.
        :param role_id: The role ID to delete.
        """
        url = (self.GUILD_BASE + "/roles/{role_id}").format(guild_id=guild_id, role_id=role_id)

        data = await self.delete(url, bucket="guild_roles:{}".format(guild_id))
        return data

    async def create_channel(self, guild_id: int, name: str, type_: int, *,
                             bitrate: int = None, user_limit: int = None,
                             permission_overwrites: list = None):
        """
        Creates a new channel.

        :param guild_id: The guild ID to create the channel in.
        :param name: The name of the channel.
        :param type_: The type of the channel (text/voice).
        :param bitrate: The bitrate of the channel, if it is a voice channel.
        :param user_limit: The maximum number of users that can be in the channel.
        :param permission_overwrites: The list of permission overwrites to use for this channel.
        """
        url = (self.GUILD_BASE + "/channels").format(guild_id=guild_id)
        payload = {
            "name": name,
            "type": type_
        }

        if type_ == 2:
            if bitrate is not None:
                payload["bitrate"] = bitrate

            if user_limit is not None:
                payload["user_limit"] = user_limit

        if permission_overwrites is not None:
            payload["permission_overwrites"] = permission_overwrites

        data = await self.post(url, bucket="guild_channels:{}".format(guild_id), json=payload)
        return data

    async def edit_channel(self, channel_id: int, *,
                           name: str = None, position: int = None,
                           topic: str = None,
                           bitrate: int = None, user_limit: int = -1):
        """
        Edits a channel.

        :param channel_id: The channel ID to edit.
        :param name: The new name of the channel.
        :param position: The new position of the channel.
        :param topic: The new topic of the channel.
        :param bitrate: The new bitrate of the channel.
        :param user_limit: The user limit of the channel.
        """
        url = self.CHANNEL_BASE.format(channel_id)
        payload = {}

        if name is not None:
            payload["name"] = name

        if position is not None:
            payload["position"] = position

        if topic is not None:
            payload["topic"] = topic

        if bitrate is not None:
            payload["bitrate"] = bitrate

        if user_limit != -1:
            payload["user_limit"] = user_limit

        data = await self.patch(url, bucket="channels:{}".format(channel_id), json=payload)
        return data

    async def delete_channel(self, channel_id: int):
        """
        Deletes a channel.

        :param channel_id: The channel ID to delete.
        """
        url = self.CHANNEL_BASE.format(channel_id)

        data = await self.delete(url, bucket="channels:{}".format(channel_id))
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

        data = await self.put(url, bucket="member_edit:{}".format(guild_id))
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

        data = await self.patch(url, bucket="member_edit:{}".format(guild_id), json=payload)
        return data

    async def change_roles_position(self, guild_id: int, role_mapping: typing.List[typing.Tuple[str, int]]):
        """
        Changes the position of a set of roles.

        :param guild_id: The guild ID that contains the roles.
        :param role_mapping: An iterable of `(role_id, new_position)` values.
        """
        url = (self.GUILD_BASE + "/roles").format(guild_id=guild_id)
        payload = [(str(r_id), position) for r_id, position in role_mapping]

        data = await self.patch(url, bucket="roles", json=payload)
        return data

    async def change_nickname(self, guild_id: int, nickname: str, *, member_id: int = None, me: bool = False):
        """
        Changes the nickname of a member.

        If `me` is True, then `member_id` is not required. Otherwise, `member_id` is required.

        :param guild_id: The guild ID that contains the member.
        :param nickname: The nickname to set, None to reset.
        :param member_id: The member ID to change the nickname of.
        :param me: If this should change our own nickname.
        """
        if me:
            url = (self.GUILD_BASE + "/members/@me/nick").format(guild_id=guild_id)
        else:
            url = (self.GUILD_BASE + "/members/{member_id}").format(guild_id=guild_id, member_id=member_id)
        payload = {
            "nick": nickname
        }

        data = await self.patch(url, bucket="member_edit:{}".format(guild_id), json=payload)
        return data

    async def edit_member_voice_state(self, guild_id: int, member_id: int, *,
                                      deaf: bool = None, mute: bool = None, channel_id: int = None):
        """
        Edits the voice state of a member.

        :param guild_id: The guild ID to edit in.
        :param member_id: The member ID to edit.
        :param deaf: Should the member be deafened?
        :param mute: Should the member be muted?
        :param channel_id: What channel should the member be moved to?
        """
        url = (self.GUILD_BASE + "/members/{member_id}").format(guild_id=guild_id, member_id=member_id)
        payload = {}

        if deaf is not None:
            payload["deaf"] = deaf

        if mute is not None:
            payload["mute"] = mute

        if channel_id is not None:
            payload["channel_id"] = channel_id

        data = await self.patch(url, bucket="member_edit:{}".format(guild_id), json=payload)
        return data

    async def modify_overwrite(self, channel_id: int, target_id: int, type_: str,
                               *, allow: int = 0, deny: int = 0):
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

    async def get_widget_status(self, guild_id: int):
        """
        Gets the current widget status information for a guild.
        
        :param guild_id: The guild ID to fetch. 
        """
        url = (self.GUILD_BASE + "/embed").format(guild_id=guild_id)

        data = await self.get(url, bucket="widget:{}".format(guild_id))
        return data

    async def get_widget_data(self, guild_id: int):
        """
        Gets the current widget data for a guild.
        
        :param guild_id: The guild ID of the widget to fetch.
        """
        url = (self.GUILD_BASE + "/widget.json").format(guild_id=guild_id)

        data = await self.get(url, bucket="widget:{}".format(guild_id))
        return data

    async def edit_widget(self, guild_id: int,
                          enabled: bool = None, channel_id: int = 0):
        """
        Edits the widget status for this guild.
        
        :param guild_id: The guild edit to edit the widget of. 
        :param enabled: Is the widget enabled in this guild? 
        :param channel_id: What channel ID is the instant invite for? This can be None to disable the channel.
        """
        url = (self.GUILD_BASE + "/embed").format(guild_id=guild_id)
        payload = {}

        if enabled is not None:
            payload["enabled"] = enabled

        if channel_id != 0:
            payload["channel_id"] = channel_id

        data = await self.patch(url, bucket="widget:{}".format(guild_id), json=payload)
        return data

    # Webhooks
    async def get_webhook(self, webhook_id: int):
        """
        Gets a webhook object for the specified ID.

        :param webhook_id: The ID of the webhook to get.
        """
        url = (self.API_BASE + "/webhooks/{webhook_id}").format(webhook_id=webhook_id)

        data = await self.get(url, bucket="webhooks")  # not a major param :(
        return data

    async def get_webhooks_for_guild(self, guild_id: int):
        """
        Gets the webhooks for the specified guild.

        :param guild_id: The ID of the guild to get the webhooks for.
        """
        url = (self.GUILD_BASE + "/webhooks").format(guild_id=guild_id)

        data = await self.get(url, bucket="webhooks:{}".format(guild_id))
        return data

    async def get_webhooks_for_channel(self, channel_id: int):
        """
        Gets the webhooks for the specified channel.

        :param channel_id: The ID of the channel to get the webhooks for.
        """
        url = (self.CHANNEL_BASE + "/webhooks").format(channel_id=channel_id)

        data = await self.get(url, bucket="webhooks:{}".format(channel_id))
        return data

    async def create_webhook(self, channel_id: int, *,
                             name: str = None, avatar: str = None):
        """
        Creates a webhook.

        :param channel_id: The channel ID to create the webhook in.
        :param name: The name of the webhook to create.
        :param avatar: The base64 encoded avatar to send.
        """
        url = (self.CHANNEL_BASE + "/webhooks").format(channel_id=channel_id)
        payload = {"name": name}

        if avatar is not None:
            payload["avatar"] = avatar

        data = await self.post(url, bucket="webhooks:{}".format(channel_id), json=payload)
        return data

    async def edit_webhook(self, webhook_id: int, *,
                           name: str = None, avatar: str = None):
        """
        Edits a webhook.

        :param webhook_id: The ID of the webhook to edit.
        :param name: The name of the webhook.
        :param avatar: The base64 encoded avatar to send.
        """
        url = (self.API_BASE + "/webhooks/{webhook_id}").format(webhook_id=webhook_id)
        payload = {}

        if avatar is not None:
            payload["avatar"] = avatar

        if name is not None:
            payload["name"] = name

        data = await self.patch(url, bucket="webhooks", json=payload)
        return data

    async def edit_webhook_with_token(self, webhook_id: int, token: str, *,
                                      name: str = None, avatar: str = None):
        """
        Edits a webhook, with a token.

        :param webhook_id: The ID of the webhook to edit.
        :param token: The token of the webhook to edit.
        :param name: The name of the webhook to edit.
        :param avatar: The base64 encoded avatar to send.
        """
        url = (self.API_BASE + "/webhooks/{webhook_id}/{token}").format(webhook_id=webhook_id, token=token)
        payload = {}

        if avatar is not None:
            payload["avatar"] = avatar

        if name is not None:
            payload["name"] = name

        data = await self.patch(url, bucket="webhooks", json=payload)
        return data

    async def delete_webhook(self, webhook_id: int):
        """
        Deletes a webhook.

        :param webhook_id: The ID of the webhook to delete.
        """
        url = (self.API_BASE + "/webhooks/{webhook_id}").format(webhook_id=webhook_id)

        data = await self.delete(url, bucket="webhooks")
        return data

    async def delete_webhook_with_token(self, webhook_id: int, token: str):
        """
        Deletes a webhook with a token.

        :param webhook_id: The ID of the webhook to delete.
        :param token: The token of the webhook.
        """
        url = (self.API_BASE + "/webhooks/{webhook_id}/{token}").format(webhook_id=webhook_id, token=token)

        data = await self.delete(url, bucket="webhooks")
        return data

    async def execute_webhook(self, webhook_id: int, webhook_token: str, *,
                              content: str = None, embeds: typing.List[typing.Dict] = None,
                              username: str = None, avatar_url: str = None,
                              wait: bool = False):
        """
        Executes a webhook.

        :param webhook_id: The ID of the webhook to execute.
        :param webhook_token: The token of this webhook.
        :param content: Any message content to send.
        :param embeds: A list of embeds to send.
        :param username: The username to override with.
        :param avatar_url: The avatar URL to send.
        :param wait: If we should wait for the message to send.
        """
        url = (self.API_BASE + "/webhooks/{webhook_id}/{token}").format(webhook_id=webhook_id, token=webhook_token)
        payload = {}

        if content:
            payload["content"] = content

        if embeds:
            payload["embeds"] = embeds

        if username:
            payload["username"] = username

        if avatar_url:
            payload["avatar_url"] = avatar_url

        # URL params, not payload
        params = {"wait": str(wait)}
        data = await self.post(url, bucket="webhooks", json=payload, params=params)

        return data

    # Invites
    async def get_invite(self, invite_code: str):
        """
        Gets an invite by code.

        :param invite_code: The invite to get.
        """
        url = (self.API_BASE + "/invites/{invite_code}").format(invite_code=invite_code)

        data = await self.get(url, bucket="invites")
        return data

    async def get_invites_for(self, guild_id: int):
        """
        Gets the invites for the specified guild.

        :param guild_id: The guild ID to get invites inside.
        """
        url = (self.GUILD_BASE + "/invites").format(guild_id=guild_id)

        data = await self.get(url, bucket="invites:{}".format(guild_id))
        return data

    async def create_invite(self, channel_id: int, *,
                            max_age: int = None, max_uses: int = None,
                            temporary: bool = None, unique: bool = None):
        """
        Creates an invite.

        :param channel_id: The channel ID to create the invite in.
        :param max_age: The maximum age of the invite.
        :param max_uses: The maximum uses of the invite.
        :param temporary: Is this invite temporary?
        :param unique: Is this invite unique?
        """
        url = (self.CHANNEL_BASE + "/invites").format(channel_id=channel_id)
        payload = {}

        if max_age is not None:
            payload["max_age"] = max_age

        if max_uses is not None:
            payload["max_uses"] = max_uses

        if temporary is not None:
            payload["temporary"] = temporary

        if unique is not None:
            payload["unique"] = unique

        data = await self.post(url, bucket="invites:{}".format(channel_id), json=payload)
        return data

    async def delete_invite(self, invite_code: str):
        """
        Deletes the invite specified by the code.

        :param invite_code: The code of the invite to delete.
        """
        url = (self.API_BASE + "/invites/{invite_code}").format(invite_code)

        data = await self.delete(url, bucket="invites")
        return data

    # User only
    async def get_user_profile(self, user_id: int):
        """
        Gets a user's profile.

        :param user_id: The user ID of the profile to fetch.
        """
        url = (self.API_BASE + "/users/{user_id}/profile").format(user_id=user_id)

        data = await self.get(url, bucket="user:get")
        return data

    async def send_friend_request(self, user_id: int):
        """
        Sends a friend request to a user.

        :param user_id: The user ID to send the request to.
        """
        url = (self.USER_ME + "/relationships/{user_id}").format(user_id=user_id)

        data = await self.put(url, bucket="user:relationships", json={})
        return data

    async def remove_relationship(self, user_id: int):
        """
        Removes a friend, cancels a friend request or unblocks a user.

        :param user_id: The user ID who is being modified.
        """
        url = (self.USER_ME + "/relationships/{user_id}").format(user_id=user_id)

        data = await self.delete(url, bucket="user:relationships")
        return data

    async def block_user(self, user_id: int):
        """
        Blocks a user.

        :param user_id: The user ID to block.
        """
        url = (self.USER_ME + "/relationships/{user_id}").format(user_id=user_id)

        data = await self.put(url, bucket="user:relationships", json={"type": 2})  # type 2 means block
        return data

    async def update_user_settings(self, **settings):
        """
        Updates the current user's settings.
        
        :param settings: The dict of settings to update. 
        """
        url = self.USER_ME + "/settings"

        data = await self.patch(url, bucket="user", json=settings)
        return data

    # Application info
    async def get_app_info(self, application_id: int):
        """
        Gets some basic info about an application.

        :param application_id: The ID of the application to get info about.
            If this is None, it will fetch the current application info.
        """
        if application_id is None:
            return await self._get_app_info_me()

        application_id = str(application_id)

        url = (self.API_BASE + "/oauth2/authorize")

        try:
            data = await self.get(url, bucket="oauth2", params={"client_id": application_id, "scope": "bot"})
        except HTTPException as e:
            if e.error_code != 50010:
                raise

            data = await self.get(url, bucket="oauth2", params={"client_id": application_id})
        return data

    async def _get_app_info_me(self):
        """
        :return: The application info for this bot.
        """
        url = self.API_BASE + "/oauth2/applications/@me"

        data = await self.get(url, "oauth2")
        # httpclient is meant to be a "pure" wrapper, but add this anyway.
        me = await self.get_user_me()

        final = {
            "application": data,
            "bot": me,
        }

        return final

    async def authorize_bot(self, application_id: int, guild_id: int,
                            *, permissions: int = 0):
        """
        Authorize a bot to be added to a guild.

        :param application_id: The client ID of the bot to be added.
        :param guild_id: The guild ID to add the bot to.
        :param permissions: The permissions to add the bot with.
        """
        url = self.API_BASE + "/oauth2/authorize"
        params = {
            "client_id": str(application_id),
            "scope": "bot"
        }

        payload = {
            "guild_id": guild_id,
            "authorize": True,
            "permissions": permissions
        }

        data = await self.post(url, "oauth2", params=params, json=payload)
        return data

    async def get_authorized_apps(self):
        """
        Gets authorized apps for this account.
        """
        url = self.API_BASE + "/oauth2/tokens"

        data = await self.get(url, bucket="oauth2")
        return data

    async def revoke_authorized_app(self, app_id: int):
        """
        Revokes an application authorization.
        
        :param app_id: The ID of the application to revoke the authorization of. 
        """
        url = (self.API_BASE + "/oauth2/tokens/{app_id}").format(app_id=app_id)

        data = await self.delete(url, bucket="oauth")
        return data

    # Misc
    async def open_private_channel(self, user_id: int):
        """
        Opens a new private channel with a user.

        :param user_id: The user ID of the user to open with.
        """
        url = self.USER_ME + "/channels"
        payload = {
            "recipient_id": user_id
        }

        data = await self.post(url, "channels:private:create", json=payload)
        return data

    async def leave_guild(self, guild_id: str):
        """
        Leaves a guild.

        :param guild_id: The guild ID of the guild to leave.
        """
        url = self.USER_ME + "/guilds/{}".format(guild_id)

        data = await self.delete(url, "guild:leave")
        return data
