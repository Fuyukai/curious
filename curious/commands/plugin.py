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
Classes for plugin objects.

.. currentmodule:: curious.commands.plugin
"""
import inspect

from curious.core import client as md_client


class Plugin(object):
    """
    Represents a plugin (a collection of events and commands under one class).
    """
    def __init__(self, client: 'md_client.Client'):
        #: The client for this plugin.
        self.client = client

    async def load(self) -> None:
        """
        Called when this plugin is loaded.

        By default, this does nothing. It is meant to be overridden to customize behaviour.
        """
        pass

    async def unload(self) -> None:
        """
        Called when this plugin is unloaded.

        By default, this does nothing. It is meant to be overridden to customize behaviour.
        """

    def _get_commands(self) -> list:
        """
        Gets the commands for this plugin.
        """
        return [i[1] for i in inspect.getmembers(self, predicate=lambda i: hasattr(i, "is_cmd"))]
