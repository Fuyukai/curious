"""
Special helpers for events.
"""


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

    :ivar client: The client instance that the event is currently connected to.
    :ivar shard_id: The shard ID that this event was sent on.
    """

    def __init__(self, cl, shard_id: int):
        self.client = cl
        self.shard_id = shard_id
        self.shard_count = cl.shard_count

    def change_status(self, *args, **kwargs):
        kwargs["shard_id"] = self.shard_id
        return self.client.change_status(*args, **kwargs)

    @property
    def gateway(self):
        return self.client._gateways[self.shard_id]
