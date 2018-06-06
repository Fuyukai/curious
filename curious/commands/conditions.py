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
Provides some built-in conditions.
"""
from curious.commands import Context, condition


def is_owner():
    """
    Ensures a command can only be ran by the bot owner.

    Called like so::

        @is_owner()
        async def mycommand(self, ctx: Context):
            ...

    """
    def _condition(ctx: Context):
        # might still be downloading (???), so we ensure it can't be ran
        if ctx.bot.application_info is None:
            return False

        return ctx.message.author_id == ctx.bot.application_info.owner.id

    return condition(_condition)


def bot_has_permission(**kwargs):
    """
    Ensures the bot has a specific permission.

    To use, pass ``name=value`` to
    """