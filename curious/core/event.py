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
Special helpers for events.

.. currentmodule: curious.core.events
"""
import functools
import inspect
import logging
import typing

import multio
from async_generator import asynccontextmanager
from multidict import MultiDict

from curious.core import client as md_client
from curious.core.gateway import GatewayHandler
from curious.util import remove_from_multidict, safe_generator

logger = logging.getLogger("curious.events")


class ListenerExit(Exception):
    """
    Raised when a temporary listener is to be exited.

    .. code-block:: python3

        def listener(ctx, message):
            if message.author.id == message.guild.owner_id:
                raise ListenerExit

    """


@asynccontextmanager
@safe_generator
async def _wait_for_manager(manager, name: str, predicate):
    """
    Helper class for managing a wait_for.
    """
    async with multio.asynclib.task_manager() as tg:
        try:
            partial = functools.partial(manager.wait_for, name, predicate)
            await multio.asynclib.spawn(tg, partial)
            yield
        finally:
            await multio.asynclib.cancel_task_group(tg)


class EventManager(object):
    """
    A manager for events.

    This deals with firing of events and temporary listeners.
    """

    def __init__(self):
        #: The task manager used to spawn events.
        self.task_manager = None

        #: A list of event hooks.
        self.event_hooks = set()

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
            raise TypeError("Event must be an async function")

        if name is None:
            evs = func.events
        else:
            evs = [name]

        for ev_name in evs:
            logger.debug("Registered event `{}` handling `{}`".format(func, ev_name))
            self.event_listeners.add(ev_name, func)

    def remove_event(self, name: str, func):
        """
        Removes a function event.

        :param name: The name the event is registered under.
        :param func: The function to remove.
        """
        self.event_listeners = remove_from_multidict(self.event_listeners, key=name, item=func)

    # listeners
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

    def add_event_hook(self, listener):
        """
        Adds an event hook.

        :param listener: The event hook callable to use.
        """
        logger.warning("Adding event hook '%s'", listener)
        self.event_hooks.add(listener)

    def remove_event_hook(self, listener):
        """
        Removes an event hook.
        """
        self.event_hooks.remove(listener)

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

    async def wait_for(self, event_name: str, predicate=None):
        """
        Waits for an event.

        Returning a truthy value from the predicate will cause it to exit and return.

        :param event_name: The name of the event.
        :param predicate: The predicate to use to check for the event.
        """
        p = multio.Promise()
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
        output = await p.wait()
        if errored:
            raise output

        # unwrap tuples, if applicable
        if len(output) == 1:
            return output[0]
        return output

    def wait_for_manager(self, event_name: str, predicate) -> 'typing.AsyncContextManager[None]':
        """
        Returns a context manager that can be used to run some steps whilst waiting for a
        temporary listener.

        .. code-block:: python

            async with client.events.wait_for_manager("member_update", predicate=...):
                await member.nickname.set("Test")

        This probably won't be needed outside of internal library functions.
        """
        return _wait_for_manager(self, event_name, predicate)

    async def spawn(self, cofunc, *args) -> typing.Any:
        """
        Spawns a new async function using our task manager.

        Usage::

            async def myfn(a, b):
                await do_some_operation(a + b)

            await events.spawn(myfn, 1, 2)

        :param cofunc: The async function to spawn.
        :param args: Args to provide to the async function.
        """
        return await multio.asynclib.spawn(self.task_manager, cofunc, *args)

    async def fire_event(self, event_name: str, *args, **kwargs):
        """
        Fires an event.

        :param event_name: The name of the event to fire.
        """
        if "ctx" not in kwargs:
            gateway = kwargs.pop("gateway")
            client = kwargs.pop("client")
            ctx = EventContext(client, gateway.gw_state.shard_id, event_name)
        else:
            ctx = kwargs.pop("ctx")

        # clobber event name
        ctx.event_name = event_name

        # always ensure hooks are ran first
        for hook in self.event_hooks:
            cofunc = functools.partial(hook, ctx, *args, **kwargs)
            await self.spawn(cofunc)

        for handler in self.event_listeners.getall(event_name, []):
            coro = functools.partial(handler, ctx, *args, **kwargs)
            coro.__name__ = handler.__name__
            await self.spawn(self._safety_wrapper, coro)

        for listener in self.temporary_listeners.getall(event_name, []):
            coro = functools.partial(self._listener_wrapper, event_name, listener, ctx,
                                     *args, **kwargs)
            await self.spawn(coro)


def event(name, scan: bool = True):
    """
    Marks a function as an event.

    :param name: The name of the event.
    :param scan: Should this event be handled in scans too?
    """

    def __innr(f):
        if not hasattr(f, "events"):
            f.events = {name}

        f.is_event = True
        f.events.add(name)
        f.scan = scan
        return f

    return __innr


def scan_events(obb) -> typing.Generator[None, typing.Tuple[str, typing.Any], None]:
    """
    Scans an object for any items marked as an event and yields them.
    """

    def _pred(f):
        is_event = getattr(f, "is_event", False)
        if not is_event:
            return False

        if not f.scan:
            return False

        return True

    for _, item in inspect.getmembers(obb, predicate=_pred):
        yield (_, item)


class EventContext(object):
    """
    Represents a special context that are passed to events.
    """

    def __init__(self, cl: 'md_client.Client', shard_id: int,
                 event_name: str):
        """
        :param cl: The :class:`.Client` instance for this event context.
        :param shard_id: The shard ID this event is for.
        :param event_name: The event name for this event.
        """
        #: The :class:`.Client` instance that this event was fired under.
        self.bot = cl

        #: The shard this event was received on.
        self.shard_id = shard_id  # type: int
        #: The shard for this bot.
        self.shard_count = cl.shard_count  # type: int

        #: The event name for this event.
        self.event_name = event_name  # type: str

    @property
    def handlers(self) -> typing.List[typing.Callable[['EventContext'], None]]:
        """
        :return: A list of handlers registered for this event. 
        """
        return self.bot.events.getall(self.event_name, [])

    async def change_status(self, *args, **kwargs) -> None:
        """
        Changes the current status for this shard.
        
        This takes the same arguments as :class:`.Client.change_status`, but ignoring the shard ID.
        """
        kwargs["shard_id"] = self.shard_id
        return await self.bot.change_status(*args, **kwargs)

    @property
    def gateway(self) -> GatewayHandler:
        """
        :return: The :class:`.Gateway` that produced this event.
        """
        return self.bot.gateways[self.shard_id]
