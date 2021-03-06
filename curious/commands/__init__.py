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
Commands helpers.

.. currentmodule:: curious.commands

.. autosummary::
    :toctree: commands

    manager
    context
    decorators
    plugin
    utils
    ratelimit
    help
    conditions

    exc
    converters
"""
from typing import Union

from curious.commands._convenience import *
from curious.commands._magic import *
from curious.commands.context import Context, current_command_context
from curious.commands.decorators import command, condition
from curious.commands.manager import CommandsManager
from curious.commands.plugin import Plugin
from curious.util import ContextVarProxy

# lie blatantly
ctx: Union[Context, ContextVarProxy[Context]] = ContextVarProxy(current_command_context)  # type: ignore
