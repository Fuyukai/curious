"""
Misc utilities shared throughout the library.
"""
import base64
import datetime

import collections
import imghdr
import inspect

import functools
import typing


class AsyncIteratorWrapper(collections.AsyncIterator):
    """
    Wraps a coroutine that returns a sequence of items into something that can iterated over asynchronously.
    
    .. code-block:: python
    
        async def a():
            # ... some long op
            return [..., ..., ...]
         
        it = AsyncIteratorWrapper(a())
        
        async for item in it:
            print(item)
    
    """

    def __init__(self, coro: typing.Awaitable[typing.List]):
        self.coro = coro

        self.items = collections.deque()

        self._filled = False

    async def _fill(self):
        self.items.extend(await self.coro)
        self._filled = True

    async def __anext__(self):
        if not self._filled:
            await self._fill()

        try:
            return self.items.popleft()
        except IndexError:
            raise StopAsyncIteration


def base64ify(image_data: bytes):
    """
    Base64-ifys an image to send to discord.

    :param image_data: The data of the image to use.
    :return: A string containing the encoded image.
    """
    # Convert the avatar to base64.
    mimetype = imghdr.what(None, image_data)
    if not mimetype:
        raise ValueError("Invalid image type")

    b64_data = base64.b64encode(image_data).decode()
    return "data:{};base64,{}".format(mimetype, b64_data)


def to_datetime(timestamp: str) -> datetime.datetime:
    """
    Converts a Discord-formatted timestamp to a datetime object.

    :param timestamp: The timestamp to convert.
    :return: The :class:`datetime.datetime` object that corresponds to this datetime.
    """
    if timestamp is None:
        return

    if timestamp.endswith("+00:00"):
        timestamp = timestamp[:-6]

    try:
        return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        # wonky datetimes
        return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")


def replace_quotes(item: str) -> str:
    """
    Replaces the quotes in a string, but only if they are un-escaped.
    
    .. code-block:: python
    
        some_weird_string = r'"this is quoted and removed" but \" that was kept and this isn't \\"'
        replace_quotes(some_weird_string)  # 'this is quoted and removed but " that was kept but this isnt \\'

    :param item: The string to scan.
    :return: The string, with quotes replaced.
    """
    # A list is used because it can be appended easily.
    final_str_arr = []

    for n, char in enumerate(item):
        # only operate if the previous char actually exists
        if n - 1 < 0:
            if char != '"':
                final_str_arr.append(char)

            continue

        # Complex quoting rules!
        # If it's a SINGLE backslash, don't append it.
        # If it's a double backslash, append it.
        if char == '\\':
            if item[n - 1] == "\\":
                # double backslash, append it
                final_str_arr.append(char)

            continue

        if char == '"':
            # check to see if it's escaped
            if item[n - 1] == '\\':
                # if the last char on final_str_arr is NOT a backslash, we want to keep it.
                if len(final_str_arr) > 0 and final_str_arr[-1] != '\\':
                    final_str_arr.append('"')

            continue

        # None of the above were hit, so add it anyway and continue.
        final_str_arr.append(char)

    return "".join(final_str_arr)


def _traverse_stack_for(t: type):
    """
    Traverses the stack for an object of type `t`.

    :param t: The type of the object.
    :return: The object, if found.
    """
    for fr in inspect.stack():
        frame = fr.frame
        try:
            locals = frame.locals
        except AttributeError:
            # idk
            continue
        else:
            for object in locals.values():
                if type(object) is t:
                    return object
        finally:
            # prevent reference cycles
            del fr


def _ad_getattr(self, key: str):
    try:
        return self[key]
    except KeyError as e:
        raise AttributeError(key) from e


attrdict = type("attrdict", (dict,), {
    "__getattr__": _ad_getattr,
    "__setattr__": dict.__setitem__,
    "__doc__": "A dict that allows attribute access as well as item access for "
               "keys."
})
