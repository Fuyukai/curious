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
Misc utilities used in commands related things.

.. currentmodule:: curious.commands.utils
"""
import inspect
from typing import Callable, Iterable, List, Union

import collections
import typing_inspect

from curious.commands.exc import ConversionFailedError, MissingArgumentError
from curious.core.client import Client
from curious.dataclasses.message import Message
from curious.util import replace_quotes


def get_full_name(func) -> str:
    """
    Gets the full name of a command, taking into account it's parents.
    """
    name = []
    # loop over and extract the name
    # then set func to the parent
    # and break if the parent is None
    while True:
        name.append(func.cmd_name)
        if func.cmd_parent is None:
            break

        func = func.cmd_parent

    return ' '.join(reversed(name))


async def _convert(ctx, tokens: List[str], signature: inspect.Signature):
    """
    Converts tokens passed from discord, using a signature.
    """
    final_args = []
    final_kwargs = {}

    def _with_reraise(func, ann, ctx, arg):
        try:
            return func(ann, ctx, arg)
        except ConversionFailedError:
            raise
        except Exception as e:
            raise ConversionFailedError(ctx, arg, ann, message="Converter error") from e

    args_it = iter(tokens)
    for n, (name, param) in enumerate(signature.parameters.items()):
        if n == 0:
            # Don't convert the `ctx` argument.
            continue

        assert isinstance(param, inspect.Parameter)
        # We loop over the signature parameters because it's easier to use those to consume.
        # Get the next argument from args.

        def consume_token() -> str:
            try:
                return next(args_it)
            except StopIteration as e:
                # not good!
                # If we're a *arg format, we can safely handle this, or if we have a default.
                if param.kind in [inspect.Parameter.KEYWORD_ONLY,
                                  inspect.Parameter.VAR_POSITIONAL]:
                    return None

                if param.default == inspect.Parameter.empty:
                    raise MissingArgumentError(ctx, param.name) from e

                return None  # ??

        # Begin the consumption!
        if param.kind in [inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          inspect.Parameter.POSITIONAL_ONLY]:
            # ensure we have a non-empty argument
            arg = consume_token()
            if arg is None:
                break

            while arg == "":
                if arg is None:
                    break

                arg = next(args_it)

            arg = replace_quotes(arg)
            converter = ctx._lookup_converter(param.annotation)
            final_args.append(_with_reraise(converter, param.annotation, ctx, arg))
            continue

        if param.kind in [inspect.Parameter.KEYWORD_ONLY]:
            # Only add it to final_kwargs.
            # This is a consume all operation, so we eat all of the arguments.
            f = []

            while True:
                next_arg = consume_token()
                if next_arg is None:
                    break

                f.append(next_arg)

            if not f:
                if param.default is inspect.Parameter.empty:
                    raise MissingArgumentError(ctx, param.name)
                else:
                    final_kwargs[param.name] = param.default
            else:
                converter = ctx._lookup_converter(param.annotation)
                if len(f) == 1:
                    final_kwargs[param.name] = _with_reraise(converter, param.annotation, ctx,
                                                             f[0])
                else:
                    final_kwargs[param.name] = _with_reraise(converter, param.annotation, ctx,
                                                             " ".join(f))
            continue

        if param.kind in [inspect.Parameter.VAR_POSITIONAL]:
            # This *shouldn't* be called on `*` arguments, but we can't be sure.
            # Special case - consume ALL the arguments.
            f = []

            while True:
                next_arg = consume_token()
                if next_arg is None:
                    break

                f.append(next_arg)

            if not f:
                if param.default is inspect.Parameter.empty:
                    raise MissingArgumentError(ctx, param.name)
                else:
                    final_kwargs[param.name] = param.default
            else:
                converter = ctx._lookup_converter(param.annotation)
                if len(f) == 1:
                    final_kwargs[param.name] = _with_reraise(converter, param.annotation, ctx,
                                                             f[0])
                else:
                    final_kwargs[param.name] = _with_reraise(converter, param.annotation, ctx,
                                                             " ".join(f))

        if param.kind in [inspect.Parameter.VAR_KEYWORD]:
            # no
            continue

    return final_args, final_kwargs


def get_description(func) -> str:
    """
    Gets the description of a function.

    :param func: The function.
    :return: The description extracted from the docstring, or None.
    """
    if not func.__doc__:
        return None

    doc = inspect.cleandoc(inspect.getdoc(func))
    lines = doc.split("\n")
    return lines[0]


def get_usage(func, invoked_as: str = None) -> str:
    """
    :return: The usage text for this command.
    """
    if invoked_as is not None:
        final = [invoked_as]
    else:
        final = [func.cmd_name]

    signature = inspect.signature(func)

    # TODO: Replace this with a proper one
    def stringify(ann):
        origin = typing_inspect.get_origin(ann)
        if not origin:
            return ann.__name__

        args = typing_inspect.get_args(ann, evaluate=True)
        return f"{origin.__name__}[{', '.join(arg.__name__ for arg in args)}]"

    for n, (name, param) in enumerate(signature.parameters.items()):
        # always skip the first arg, as it's self/ctx
        if n == 0:
            continue

        # check if we should skip the 2nd arg
        # not always possible
        from curious.commands.context import Context
        if name in ["ctx", "context"] or param.annotation is Context:
            continue

        # switch based on kind (again...)
        assert isinstance(param, inspect.Parameter)
        if param.kind in [inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          inspect.Parameter.POSITIONAL_ONLY]:
            if param.annotation is not inspect.Parameter.empty:
                s = "<{}: {}>".format(param.name, stringify(param.annotation))
            else:
                s = "<{}>".format(param.name)

        elif param.kind in [inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_POSITIONAL]:
            if param.default is not inspect.Parameter.empty:
                if param.annotation is not inspect.Parameter.empty:
                    s = "[{}: {} (default: {})]".format(param.name, stringify(param.annotation),
                                                        repr(param.default))
                else:
                    s = "[{} (default: {})]".format(param.name, repr(param.default))
            else:
                if param.annotation is not inspect.Parameter.empty:
                    s = "<{}: {}>".format(param.name, stringify(param.annotation))
                else:
                    s = "<{}>".format(param.name)
        else:
            s = ""

        final.append(s)

    return " ".join(final)


# This function is a modified version of the code taken from https://stackoverflow.com/a/43035638.
# This function is licenced under the MIT Licence. (C) 2017 THE_MAD_KING.
# See: https://meta.stackexchange.com/questions/272956/a-new-code-license-the-mit-this-time-with
# -attribution-required
# You can find a copy of the MIT Licence at https://opensource.org/licenses/MIT.
def split_message_content(content: str, delim: str = " ") -> List[str]:
    """
    Splits a message into individual parts by `delim`, returning a list of strings.
    This method preserves quotes.

    .. code-block:: python3

        content = '!send "Fuyukai desu" "Hello, world!"'
        split = split_message_content(content, delim=" ")

    :param content: The message content to split.
    :param delim: The delimiter to split on.
    :return: A list of items split
    """

    tokens = []
    cur = ''
    in_quotes = False

    for char in content.strip():
        if char == delim and not in_quotes:
            tokens.append(cur)
            cur = ''
        elif char == '"' and not in_quotes:
            in_quotes = True
            cur += char
        elif char == '"' and in_quotes:
            in_quotes = False
            cur += char
        else:
            cur += char
    tokens.append(cur)

    return tokens


def prefix_check_factory(prefix: Union[str, Iterable[str], Callable[[Client, Message], str]]):
    """
    The default message function factory.

    This provides a callable that will fire a command if the message begins with the specified
    prefix or list of prefixes.

    If ``command_prefix`` is provided to the :class:`.Client`, then it will automatically call this
    function to get a message check function to use.

    .. code-block:: python3

        # verbose form
        message_check = prefix_check_factory(["!", "?"])
        cl = Client(message_check=message_check)

        # implicit form
        cl = Client(command_prefix=["!", "?"])

    The :attr:`prefix` is set on the returned function that can be used to retrieve the prefixes
    defined to create  the function at any time.

    :param prefix: A :class:`str` or :class:`typing.Iterable[str]` that represents the prefix(es) \
        to use.
    :return: A callable that can be used for the ``message_check`` function on the client.
    """

    async def __inner(bot: Client, message: Message):
        # move prefix out of global scope
        _prefix = prefix
        matched = None

        if callable(_prefix):
            _prefix = _prefix(bot, message)
            if inspect.isawaitable(_prefix):
                _prefix = await _prefix

        if isinstance(_prefix, str):
            match = message.content.startswith(_prefix)
            if match:
                matched = _prefix

        elif isinstance(prefix, collections.Iterable):
            for i in _prefix:
                if message.content.startswith(i):
                    matched = i
                    break

        if not matched:
            return None

        tokens = split_message_content(message.content[len(matched):])
        command_word = tokens[0]

        return command_word, tokens[1:]

    __inner.prefix = prefix
    return __inner
