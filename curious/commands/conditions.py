"""
Commonly used conditions.

.. currentmodule:: curious.commands.conditions
"""

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


def author_has_roles(*roles, bypass_owner=True):
    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        author_roles = [role.name for role in ctx.author.roles]
        return all(role in author_roles for role in roles)

    return condition(_condition, bypass_owner=bypass_owner)


def bot_has_roles(*roles, bypass_owner=False):
    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        bot_roles = [role.name for role in ctx.guild.me.roles]
        return all(role in bot_roles for role in roles)

    return condition(_condition, bypass_owner=bypass_owner)
