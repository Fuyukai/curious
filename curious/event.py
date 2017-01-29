"""
Special helpers for events.
"""


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
