"""
Classes for plugin objects.
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
