"""
Utilities for ratelimiting a command.
"""
import time
from typing import Any, Callable, List, Tuple

from curious.commands import Context
from curious.commands.exc import CommandRateLimited


class BucketNamer:
    """
    A simple namespace for storing bucket functions.
    """

    def __new__(cls):
        raise NotImplementedError("Don't make an instance of this class")

    @staticmethod
    def GUILD(ctx: Context) -> str:
        """
        A bucket namer that uses the guild ID as the bucket.
        """
        return str(ctx.guild.id)

    @staticmethod
    def CHANNEL(ctx: Context) -> str:
        """
        A bucket namer that uses the channel ID as the bucket.
        """
        return str(ctx.channel.id)

    @staticmethod
    def AUTHOR(ctx: Context) -> str:
        """
        A bucket namer that uses the author ID as the bucket.
        """
        return str(ctx.author.id)

    @staticmethod
    def GLOBAL(ctx: Context) -> str:
        """
        A bucket namer that is global.
        """
        return "GLOBAL"


class CommandRateLimit(object):
    """
    Represents a ratelimit for a command.
    """

    def __init__(self, *, limit: int, time: float,
                 bucket_namer: Callable[[Context], str] = BucketNamer.AUTHOR):
        """
        :param limit: The number of times a command can be called in the specified limit.
        :param time: The time (in seconds) this ratelimit lasts.
        :param bucket_namer: A callable that gets the ratelimit bucket name.
        """
        self.limit = limit
        self.time = time
        self.bucket_namer = bucket_namer

        #: The command function being used.
        self.command = None

    def get_full_bucket_key(self, ctx: Context) -> Tuple[str, str]:
        """
        Gets the full bucket key for this ratelimit.
        """
        return self.command.cmd_name, self.bucket_namer(ctx)


class RateLimiter(object):
    """
    Represents a ratelimiter. This ensures that commands meet the ratelimit before being ran.
    """

    def __init__(self):
        self._ratelimit_buckets = {}

    async def update_bucket(self, key: Any, current_uses: int, expiration: float):
        """
        Updates a ratelimit bucket.

        :param key: The ratelimit key to use.
        :param current_uses: The current uses for the key.
        :param expiration: When the ratelimit expires.
        """
        self._ratelimit_buckets[key] = (current_uses, expiration)

    async def get_bucket(self, key: Any) -> Tuple[int, float]:
        """
        Gets the ratelimit bucket for the specified key.

        :param key: The key to use.
        :return: A two-item tuple of (uses, expiration), or None if no bucket was found.
        """
        return self._ratelimit_buckets.get(key)

    async def ensure_ratelimits(self, ctx: Context, cmd):
        """
        Ensures the ratelimits for a command.
        """
        ratelimits: List[CommandRateLimit] = cmd.cmd_ratelimits
        for limit in ratelimits:
            bucket_key = limit.get_full_bucket_key(ctx)
            bucket = await self.get_bucket(key=bucket_key)
            if not bucket:
                await self.update_bucket(bucket_key, 1, time.monotonic() + limit.time)
                continue

            # check if we've hit the limit
            if bucket[0] == limit.limit:
                # we have, but that might be okay if the timer has expired
                if time.monotonic() > bucket[1]:
                    # we're good, so we can just reset the bucket and continue on our way
                    await self.update_bucket(bucket_key, 1, time.monotonic() + limit.time)
                else:
                    raise CommandRateLimited(ctx, cmd, limit, bucket)
            else:
                # we haven't, but we need to up the number anyway
                await self.update_bucket(bucket_key, bucket[0] + 1, bucket[1])
