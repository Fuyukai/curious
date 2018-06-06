"""
Commonly used conditions.

.. currentmodule:: curious.commands.conditions
"""
from typing import Union, List

from curious import Member, User
from curious.commands import Context, condition


def is_owner():
    def _condition(ctx: Context):
        # If the application info request has not been completed
        # yet we cannot guarantee the command could be ran.
        if ctx.bot.application_info is None:
            return False

        owner = ctx.bot.application_info.owner
        return ctx.author.id == owner.id

    return condition(_condition)


def author_has_permissions(bypass_owner=True, **permissions):
    def _condition(ctx: Context):
        perms = ctx.channel.permissions(ctx.author)
        return all(getattr(perms, name, None) == value
                   for name, value in permissions.items())

    return condition(_condition, bypass_owner=bypass_owner)


def bot_has_permissions(bypass_owner=False, **permissions):
    def _condition(ctx: Context):
        perms = ctx.channel.me_permissions
        return all(getattr(perms, name, None) == value
                   for name, value in permissions.items())

    return condition(_condition, bypass_owner=bypass_owner)


author_has_perms = author_has_permissions
bot_has_perms = bot_has_permissions
