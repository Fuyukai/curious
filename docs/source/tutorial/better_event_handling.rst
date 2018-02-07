.. _better_event_handling:

Better Event Handling
=====================

Curious comes with several ways to fine-tune your event handling in your bot.

.. note::

    A full list of events can be found at :doc:`../events`.

Basic Event Listeners
---------------------

Basic event listeners are the easiest way to handle events coming in from the bot. All event
listeners take a :class:`.EventContext` as their first argument, and various other arguments
depending on the event.

.. code-block:: python3

    # simple client event
    @client.event("guild_member_add")
    async def member_joined(ctx, member: Member):
        print("Member", member.name, "joined!")

Basic event listeners can also be inside plugins:

.. code-block:: python3

    from curious import event

    class MyPlugin(Plugin):
        @event("guild_member_add")
        async def member_joined(self, ctx, member: Member):
            print("Member", member.name, "joined!")

You can also add them manually to the event manager, but you **must** decorate them with the
:meth:`.event` decorator.

.. code-block:: python3

    from curious import event

    @event("guild_member_add")
    async def member_joined(ctx, member: Member):
        print("Member", member.name, "joined!")

    client.events.add_event(member_join)

The event decorator sets some attributes on on the function object that are introspected to
register the event handler.

Finally, you can have multiple events on one function, but this is usually discouraged in favour
of `Event Hooks`_.

.. code-block:: python

    @event("ready")
    @event("connect")
    async def my_function(ctx): ...

Temporary Listeners
-------------------

Temporary listeners are a way of listening to an event temporarily until a condition happens.
This is used to implement waiting for a specific event, for example.

A listener is roughly the same as an event handler, but only sticks around for a short while;
that is, until it either raises an exception (which is logged) or it raises ListenerExit. Either
one will remove it from the list of temporary listeners; and it will not get any more events.

To add a listener, you can use :meth:`.EventManager.add_temporary_listener`:

.. code-block:: python3

    # example: adding messages to a queue until STOP is sent
    async def message_listener(ctx, message: Message):
        if message.content == "STOP":
            raise ListenerExit

        await my_queue.add(message)

    client.events.add_temporary_listener("message_create", message_listener)

If you wish to remove a listener early, then you can do so with
:meth:`.EventManager.remove_listener_early`; however, it is probably better to use ListenerExit
appropriately.

Waiting For Events
------------------

Waiting for events from the websocket is a common usecase; curious provides some helper methods
to allow waiting for these events easily.

 - :meth:`.EventManager.wait_for` allows waiting for an event based on a predicate.
 - :meth:`.EventManager.wait_for_manager` is a context-manager version of ``wait_for``.

Both of these methods take an event name to listen to, and a predicate that should return
True/False based on if this is an event you want. The return result of ``wait_for`` is the normal
arguments provided to the event, without the :class:`.EventContext`.

.. code-block:: python3

    pred = lambda message: message.content == "STOP"
    stop_message = await client.wait_for("message_create", pred)  # shortcut for EventManager

:meth:`.EventManager.wait_for_manager` is not often useful inside user code.

Event Hooks
-----------

The final way of managing events is with event hooks. These are hooks that are called upon every
single event fired by the event manager, and can be useful for sub-dispatchers that filter events.
To register an event hook, use :meth:`.EventManager.add_event_hook`.

.. code-block:: python3

    async def my_hook(ctx: EventContext, *args):
        if ctx.event_name.startswith("guild_"):
            # do something

    client.events.add_event_hook(my_hook)

.. warning::

    An event hook crashing will bring down the entire bot. Be warned.
