"""
Commonly used conditions.

.. currentmodule:: curious.commands.conditions
"""
from functools import partial, wraps

from curious.commands import Context, condition, CommandsManager
from curious.commands.exc import ConditionsFailedError


def is_owner_check(ctx):
    # If the application info request has not been completed
    # yet we cannot guarantee the command could be ran.
    if ctx.bot.application_info is None:
        return False

    owner = ctx.bot.application_info.owner
    return ctx.author.id == owner.id


def owner_bypass(deco):
    @wraps(deco)
    def decorator_wrap(owner_bypass=True):
        def decorator(func):
            if owner_bypass is not True:
                return func

            @wraps(func)
            async def inner(ctx, *args, **kwargs):
                if is_owner_check(ctx):
                    return func(ctx, *args, **kwargs)
                can_run, failed = await ctx.can_run(func)

                if failed:
                    raise ConditionsFailedError(ctx, failed)
                return func(ctx, *args, **kwargs)

            return inner

        return decorator

    return decorator_wrap


def is_owner():
    return condition(is_owner_check)
