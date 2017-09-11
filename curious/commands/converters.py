"""
Converter methods.
"""
from curious.commands.exc import ConversionFailedError
from curious.dataclasses.channel import Channel
from curious.dataclasses.member import Member


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
        member = ctx.guild.find_member(arg)
        if not member:
            raise ConversionFailedError(ctx, arg, Member)

    return member


def convert_channel(ctx, arg: str) -> Channel:
    """
    Converts an argument into a Channel.
    """
    if arg.startswith("<#") and arg.endswith(">"):
        id = arg[2:-1]

        try:
            id = int(id)
        except ValueError:
            raise ConversionFailedError(ctx, arg, Channel)

        channel = ctx.guild.channels.get(id)
        if not channel:
            raise ConversionFailedError(ctx, arg, Channel)
    else:
        try:
            channel = next(filter(lambda c: c.name == arg, ctx.guild.channels.values()), None)
            if channel is None:
                channel = ctx.guild.channels.get(int(arg))
        except (StopIteration, ValueError):
            raise ConversionFailedError(ctx, arg, Channel)
        else:
            if channel is None:
                raise ConversionFailedError(ctx, arg, Channel)

    return channel


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
