"""
Special helpers for events.
"""
import inspect
import logging
import typing

import curio
from multidict import MultiDict

from curious.core import client as md_client
from curious.util import remove_from_multidict

logger = logging.getLogger("curious.events")


class ListenerExit(Exception):
    """
    Raised when a temporary listener is to be exited.

    .. code-block:: python3

        def listener(ctx, message):
            if message.author.id == message.guild.owner_id:
                raise ListenerExit

    """


class EventManager(object):
    """
    A manager for events.

    This deals with firing of events and temporary listeners.
    """

    def __init__(self):
        #: A list of event hooks.
        self.event_hooks = []

        #: A MultiDict of event listeners.
        self.event_listeners = MultiDict()

        #: A MultiDict of temporary listeners.
        self.temporary_listeners = MultiDict()

    # add or removal functions
    # Events
    def add_event(self, func, name: str = None):
        """
        Add an event to the internal registry of events.

        :param name: The event name to register under.
        :param func: The function to add.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Event must be a coroutine function")

        if name is None:
            evs = func.events
        else:
            evs = [name]

        for ev_name in evs:
            logger.debug("Registered event `{}` handling `{}`".format(func, name))
            self.event_listeners.add(ev_name, func)

    def remove_event(self, name: str, func):
        """
        Removes a function event.

        :param name: The name the event is registered under.
        :param func: The function to remove.
        """
        self.event_listeners = remove_from_multidict(self.event_listeners, key=name, item=func)

    def add_temporary_listener(self, name: str, listener):
        """
        Adds a new temporary listener.

        To remove the listener, you can raise ListenerExit which will exit it and remove the
        listener from the list.

        :param name: The name of the event to listen to.
        :param listener: The listener function.
        """
        self.temporary_listeners.add(name, listener)

    def remove_listener_early(self, name: str, listener):
        """
        Removes a temporary listener early.

        :param name: The name of the event the listener is registered under.
        :param listener: The listener function.
        """
        self.event_listeners = remove_from_multidict(self.event_listeners, key=name, item=listener)

    # wrapper functions
    async def _safety_wrapper(self, func, *args, **kwargs):
        """
        Ensures a coro's error is caught and doesn't balloon out.
        """
        try:
            await func(*args, **kwargs)
        except Exception as e:
            logger.exception("Unhandled exception in {}!".format(func.__name__), exc_info=True)

    async def _listener_wrapper(self, key: str, func, *args, **kwargs):
        """
        Wraps a listener, ensuring ListenerExit is handled properly.
        """
        try:
            await func(*args, **kwargs)
        except ListenerExit:
            # remove the function
            self.temporary_listeners = remove_from_multidict(self.temporary_listeners, key, func)
        except Exception:
            logger.exception("Unhandled exception in listener {}!".format(func.__name__),
                             exc_info=True)
            self.temporary_listeners = remove_from_multidict(self.temporary_listeners, key, func)

    async def wait_for(self, event_name: str, predicate = None):
        """
        Waits for an event.

        Returning a truthy value from the predicate will cause it to exit and return.

        :param event_name: The name of the event.
        :param predicate: The predicate to use to check for the event.
        """
        p = curio.Promise()
        errored = False

        async def listener(ctx, *args):
            # exit immediately if the predicate is none
            if predicate is None:
                await p.set(args)
                raise ListenerExit

            try:
                res = predicate(*args)
                if inspect.isawaitable(res):
                    res = await res
            except ListenerExit:
                # ???
                await p.set(args)
                raise
            except Exception as e:
                # something bad happened, set exception and exit
                logger.exception("Exception in wait_for predicate!")
                # signal that an error happened
                nonlocal errored
                errored = True
                await p.set(e)
                raise ListenerExit
            else:
                # exit now if result is true
                if res is True:
                    await p.set(args)
                    raise ListenerExit

        self.add_temporary_listener(name=event_name, listener=listener)
        output = await p.get()
        if errored:
            raise output

        # unwrap tuples, if applicable
        if len(output) == 1:
            return output[0]
        return output

    async def fire_event(self, event_name: str, *args, **kwargs):
        """
        Fires an event.

        :param event_name: The name of the event to fire.
        """
        if "ctx" not in kwargs:
            gateway = kwargs.pop("gateway")
            client = kwargs.pop("client")
            ctx = EventContext(client, gateway.shard_id, event_name)
        else:
            ctx = kwargs.pop("ctx")

        # always ensure hooks are ran first
        for hook in self.event_hooks:
            await curio.spawn(hook(ctx, *args, **kwargs), daemon=True)

        for handler in self.event_listeners.getall(event_name, []):
            coro = self._safety_wrapper(handler, ctx, *args, **kwargs)
            await curio.spawn(coro, daemon=True)

        for listener in self.temporary_listeners.getall(event_name, []):
            coro = self._listener_wrapper(event_name, listener, ctx, *args, **kwargs)
            await curio.spawn(coro, daemon=True)


def event(name, scan: bool = True):
    """
    Marks a function as an event.

    :param name: The name of the event.
    :param scan: Should this event be handled in scans too?
    """

    def __innr(f):
        if not hasattr(f, "events"):
            f.events = set()

        f.is_event = True
        f.events.add(name)
        f.scan = scan
        return f

    return __innr


class EventContext(object):
    """
    Represents a special context that are passed to events.
    """

    def __init__(self, cl: 'md_client.Client', shard_id: int,
                 event_name: str):
        #: The :class:`.Client` instance that this event was fired under.
        self.bot = cl

        #: The shard this event was received on.
        self.shard_id: int = shard_id
        #: The shard for this bot.
        self.shard_count: int = cl.shard_count

        #: The event name for this event.
        self.event_name: str = event_name

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
        return self.bot.gateways[self.shard_id]
