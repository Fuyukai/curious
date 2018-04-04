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
Converter methods.

.. currentmodule:: curious.commands.converters
"""
from typing import Any, List

import typing_inspect

from curious.commands.exc import ConversionFailedError
from curious.dataclasses.channel import Channel
from curious.dataclasses.member import Member
from curious.dataclasses.role import Role


def convert_member(ann, ctx, arg: str) -> Member:
    """
    Converts an argument into a Member.
    """
    member_id = None
    if arg.startswith("<@") and arg.endswith(">"):
        id = arg[2:-1]
        if id[0] == "!":  # strip nicknames
            id = id[1:]

        try:
            member_id = int(id)
        except ValueError:
            raise ConversionFailedError(ctx, arg, Member, "Invalid member ID")
    elif all(i.isdigit() for i in arg):
        member_id = int(arg)

    if member_id is not None:
        member = ctx.guild.members.get(member_id)
    else:
        member = ctx.guild.search_for_member(full_name=arg)

    if member is None:
        raise ConversionFailedError(ctx, arg, Member, "Could not find Member")

    return member


def convert_channel(ann, ctx, arg: str) -> Channel:
    """
    Converts an argument into a Channel.
    """
    channel_id = None
    if arg.startswith("<#") and arg.endswith(">"):
        try:
            channel_id = int(arg[2:-1])
        except ValueError:
            raise ConversionFailedError(ctx, arg, Channel, "Invalid channel ID")
    elif all(i.isdigit() for i in arg):
        channel_id = int(arg)

    if channel_id is not None:
        channel = ctx.guild.channels.get(channel_id)
    else:
        channel = next(filter(lambda c: c.name == arg, ctx.guild.channels.values()), None)

    if channel is None:
        raise ConversionFailedError(ctx, arg, Channel, "Could not find channel")

    return channel


def convert_role(ann, ctx, arg: str) -> Role:
    """
    Converts an argument into a :class:`.Role`.
    """
    role_id = None
    if arg.startswith("<@&") and arg.endswith(">"):
        try:
            role_id = int(arg[3:-1])
        except ValueError:
            raise ConversionFailedError(ctx, arg, Role, "Invalid role ID")
    elif all(i.isdigit() for i in arg):
        role_id = int(arg)

    if role_id is not None:
        role = ctx.guild.roles.get(role_id)
    else:
        role = next(filter(lambda c: c.name == arg, ctx.guild.roles.values()), None)

    if role is None:
        raise ConversionFailedError(ctx, arg, Role, "Could not find role")

    return role


def convert_int(ann, ctx, arg: str) -> int:
    """
    Converts an argument into an integer.
    """
    try:
        return int(arg, 0)
    except ValueError as e:
        raise ConversionFailedError(ctx, arg, int, "Invalid integer") from e


def convert_float(ann, ctx, arg: str) -> float:
    """
    Converts an argument into a float.
    """
    try:
        return float(arg)
    except ValueError as e:
        raise ConversionFailedError(ctx, arg, float, "Invalid float") from e


def convert_list(ann, ctx, arg: str) -> List[Any]:
    """
    Converts a :class:`typing.List`.
    """
    internal = typing_inspect.get_args(ann)[0]
    converter = ctx._lookup_converter(internal)
    sp = arg.split(" ")
    results = []

    for arg in sp:
        results.append(converter(internal, ctx, arg))

    return results


def convert_union(ann, ctx, arg: str) -> Any:
    """
    Converts a :class:`typing.Union`.

    This works by finding every type defined in the union, and trying each one until one returns
    a non-error.
    """
    subtypes = typing_inspect.get_args(ann, evaluate=True)
    for subtype in subtypes:
        try:
            converter = ctx._lookup_converter(subtype)
            return converter(ann, ctx, arg)
        except ConversionFailedError:
            continue

    raise ConversionFailedError(ctx, arg, ann, message="Failed to convert to any of these types")
