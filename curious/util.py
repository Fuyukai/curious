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

"""
Misc utilities shared throughout the library.

.. currentmodule:: curious.util
"""
import base64
import collections
import datetime
import functools
import imghdr
import inspect
import textwrap
import types
import warnings
from typing import Any, Awaitable, Callable, Coroutine, List, Union

import multio
from multidict import MultiDict

NO_ITEM = object()


def remove_from_multidict(d: MultiDict, key: str, item: Any):
    """
    Removes an item from a multidict key.
    """
    # works by popping all, removing, then re-adding into
    i = d.popall(key, [])
    if item in i:
        i.remove(item)

    for n in i:
        d.add(key, n)

    return d


class AsyncIteratorWrapper(collections.AsyncIterator):
    """
    Wraps a coroutine that returns a sequence of items into something that can iterated over
    asynchronously.
    
    .. code-block:: python3
    
        async def a():
            # ... some long op
            return [..., ..., ...]
         
        it = AsyncIteratorWrapper(a)
        
        async for item in it:
            print(item)
    
    """

    def __init__(self, coro: Callable[[], Union[Awaitable[List[Any]], Coroutine[None, None, Any]]]):
        self.coro = coro

        self.items = collections.deque()

        self._filled = False

    async def _fill(self) -> None:
        self.items.extend(await self.coro())
        self._filled = True

    async def __anext__(self) -> Any:
        if not self._filled:
            await self._fill()

        try:
            return self.items.popleft()
        except IndexError:
            raise StopAsyncIteration

    # helper methods
    async def next(self, default=NO_ITEM) -> Any:
        """
        Gets the next item from this iterable.
        """
        try:
            return await self.__anext__()
        except StopAsyncIteration:
            if default == NO_ITEM:
                raise

            return default

    async def all(self) -> List[Any]:
        """
        Gets a flattened list of items from this iterator.
        """
        items = []

        async for item in self:
            items.append(item)

        return items


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
    
    .. code-block:: python3
    
        some_weird_string = r'"this is quoted and removed" but \" that was kept and this isn't \\"'
        replace_quotes(some_weird_string)  # 'this is quoted and removed but " that was kept but
        this isnt \\'

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
    Traverses the stack for an object of type ``t``.

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


async def coerce_agen(gen):
    """
    Coerces an async generator into a list.
    """
    results = []
    async with multio.asynclib.finalize_agen(gen) as agen:
        async for i in agen:
            results.append(i)

    return results


def subclass_builtin(original: type):
    """
    Subclasses an immutable builtin, providing method wrappers that return the subclass instead
    of the original.
    """

    def get_wrapper(subclass, func):

        @functools.wraps(func)
        def __inner_wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            new = subclass(result)

            # copy the parent dataclass if we need to
            if 'parent' in self.__dict__:
                new.__dict__['parent'] = self.__dict__['parent']

            return new

        return __inner_wrapper

    def wrapper(subclass):
        if hasattr(subclass, "__slots__"):
            raise RuntimeError("Cannot fix a slotted class")

        # get all of the methods on the original andparse the docstring; these are in a
        # well-defined format for builtins
        for meth_name in dir(original):
            func = getattr(subclass, meth_name)

            # only overwrite doc'd functions
            if not func.__doc__:
                continue

            sig = func.__doc__.split("\n")[0]

            try:
                rtype: str = sig.split("->")[1]
            except IndexError:
                continue

            # check if it matches our real method
            rtype = rtype.lstrip().rstrip()
            if rtype == original.__name__:
                # make a new function wrapper, which returns the appropriate type
                # then add it to our subclass
                wrapper = get_wrapper(subclass, func)
                setattr(subclass, meth_name, wrapper)

        return subclass

    return wrapper


class CuriousDeprecatedWarning(FutureWarning):
    """
    Warned when a function is deprecated.
    """


def deprecated(*, since: str, see_instead, removal: str):
    """
    Marks a method as deprecated.

    :param since: The version since this is deprecated.
    :param see_instead: What method to see instead.
    :param removal: The version this function will be removed at.
    """

    # TODO: In 3.7, the globals mess probably won't be needed.
    def inner(func):
        # calculate a new doc
        nonlocal see_instead
        if not isinstance(see_instead, str):
            qualname = see_instead.__qualname__
            mod = inspect.getmodule(see_instead).__name__

            # eat curious defines
            if mod.startswith("curious."):
                mod = ""

            # check for classes
            if '.' in qualname:
                see_instead = f":meth:`{mod}.{qualname}`"
            else:
                see_instead = f":func:`{mod}.{qualname}`"

        doc = inspect.getdoc(func)
        if doc is not None:
            original_doc = textwrap.dedent(func.__doc__)
            func.__doc__ = f"**This function is deprecated since {since}.** " \
                           f"See :meth:`.{see_instead}` instead.  \n" \
                           f"It will be removed at version {removal}.\n\n" \
                           f"{original_doc}"

        def wrapper(*args, **kwargs):
            warnings.warn(f"    This function is deprecated since {since}. "
                          f"    See '{see_instead}' instead.",
                          category=CuriousDeprecatedWarning, stacklevel=2)
            return func(*args, **kwargs)

        # HACKY METAPROGRAMMING
        new_globals = {**func.__globals__}
        new_globals.update(wrapper.__globals__)

        new_wrapper = types.FunctionType(
            wrapper.__code__, new_globals,
            name=wrapper.__name__, argdefs=wrapper.__defaults__,
            closure=wrapper.__closure__
        )
        new_wrapper = functools.update_wrapper(new_wrapper, func)

        new_wrapper.deprecated = True
        new_wrapper.__doc__ = inspect.getdoc(func)
        return new_wrapper

    return inner


def safe_generator(cbl):
    # only wrap if we have curio
    try:
        from curio.meta import safe_generator
        return safe_generator(cbl)
    except ModuleNotFoundError:
        return cbl


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
