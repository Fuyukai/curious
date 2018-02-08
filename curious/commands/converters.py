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
from curious.commands.exc import ConversionFailedError
from curious.dataclasses.channel import Channel
from curious.dataclasses.member import Member
from curious.dataclasses.role import Role


def convert_member(ctx, arg: str) -> Member:
    """
    Converts an argument into a Member.
    """
    if arg.startswith("<@") and arg.endswith(">"):
        # Parse the mention out
        id = arg[2:-1]
        if id[0] == "!":  # nicknames
            id = id[1:]

        try:
            id = int(id)
        except ValueError:
            raise ConversionFailedError(ctx, arg, Member)

        member = ctx.guild.members.get(id)
        if not member:
            raise ConversionFailedError(ctx, arg, Member)
    else:
        member = ctx.guild.search_for_member(full_name=arg)
        if not member:
            raise ConversionFailedError(ctx, arg, Member)

    return member


def convert_channel(ctx, arg: str) -> Channel:
    """
    Converts an argument into a Channel.
    """
    channel_id = None
    if arg.startswith("<#") and arg.endswith(">"):
        try:
            channel_id = int(arg[2:-1])
        except ValueError:
            raise ConversionFailedError(ctx, arg, Channel)
    elif all(i.isdigit() for i in arg):
        channel_id = int(arg)

    if channel_id is not None:
        try:
            channel = ctx.guild.channels[channel_id]
        except KeyError as e:
            raise ConversionFailedError(ctx, arg, Channel) from e
    else:
        try:
            channel = next(filter(lambda c: c.name == arg, ctx.guild.channels.values()))
        except (StopIteration, ValueError) as e:
            raise ConversionFailedError(ctx, arg, Channel) from e

    if channel is None:
        raise ConversionFailedError(ctx, arg, Channel)

    return channel


def convert_role(ctx, arg: str) -> Role:
    """
    Converts an argument into a :class:`.Role`.
    """
    if arg.startswith("<@&") and arg.endswith(">"):
        try:
            role_id = int(arg[3:-1])
        except ValueError:
            raise ConversionFailedError(ctx, arg, Role)
    elif all(i.isdigit() for i in arg):
        role_id = int(arg)
    else:
        role_id = None

    if role_id is not None:
        try:
            role = ctx.guild.roles[role_id]
        except KeyError as e:
            raise ConversionFailedError(ctx, arg, Role)
    else:
        try:
            role = next(filter(lambda c: c.name == arg, ctx.guild.roles.values()))
        except (StopIteration, ValueError) as e:
            raise ConversionFailedError(ctx, arg, Role) from e

    if role is None:
        raise ConversionFailedError(ctx, arg, Channel)

    return role


def convert_int(ctx, arg: str) -> int:
    """
    Converts an argument into an integer.
    """
    try:
        return int(arg)
    except ValueError as e:
        raise ConversionFailedError(ctx, arg, int) from e


def convert_float(ctx, arg: str) -> float:
    """
    Converts an argument into a float.
    """
    try:
        return float(arg)
    except ValueError as e:
        raise ConversionFailedError(ctx, arg, float) from e
