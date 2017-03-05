"""
Special helpers for events.
"""
import typing

from curious.dataclasses.user import User


def event(name, scan: bool=True):
    """
    Marks a function as an event.

    :param name: The name of the event.
    :param scan: Should this event be handled in scans too?
    """

    def __innr(f):
        f.event = name
        f.scan = scan
        return f

    return __innr


class EventContext(object):
    """
    Represents a special context that are passed to events.
    """

    def __init__(self, cl, shard_id: int,
                 event_name: str):
        #: The :class:`~.Client` instance that this event was fired under.
        self.bot = cl

        # shard info
        #: The shard this event was received on.
        self.shard_id = shard_id
        #: The shard for this bot.
        self.shard_count = cl.shard_count

        #: The event name for this event.
        self.event_name = event_name

    @property
    def user(self) -> User:
        """
        :return: The :class:`~.User` associated with this event. 
        """
        return self.bot.user

    @property
    def handlers(self) -> typing.List[typing.Callable[['EventContext'], None]]:
        """
        :return: A list of handlers registered for this event. 
        """
        return self.bot.events.getall(self.event_name, [])

    def change_status(self, *args, **kwargs):
        """
        Changes the current status for this shard.
        
        This takes the same arguments as :class:`~.Client.change_status`, but ignoring the shard ID.
        """
        kwargs["shard_id"] = self.shard_id
        return self.bot.change_status(*args, **kwargs)

    @property
    def gateway(self):
        """
        :return: The :class:`~.Gateway` that produced this event. 
        """
        return self.bot._gateways[self.shard_id]
