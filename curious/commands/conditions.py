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
