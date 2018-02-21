.. _commands:

Command Handling
================

The biggest use case of nearly every bot is to run actions in response to commands. Curious comes
with built-in commands managers for this purpose.


The Commands Manager
--------------------

The :class:`.CommandsManager` is the main way to attach commands to the client.

First, you need to create the manager and attach it to a client:

.. code-block:: python3

    # form 1, automatically register with the client
    manager = CommandsManager.with_client(bot)

    # form 2, manually register
    manager = CommandsManager(bot)
    manager.register_events()

This is required to add the handler events to the client.

Next, you need to register a message check handler. This is a callable that is called for every
message to try and extract the command from a message, if it matches. By default, the manager
provides an easy way to use a simple command prefix:

.. code-block:: python3

    # at creation time
    manager = CommandsManager(bot, command_prefix="!")

    # or set it on the manager
    manager.command_prefix = "!"

At this point, the command prefix will be available on the manager with either
:attr:`.Manager.command_prefix` or :attr:`.Manager.message_check.prefix`.

If you need more complex message checking, you can use ``message_check``:

.. code-block:: python3

    manager = CommandsManager(bot, message_check=my_message_checker)
    # or
    manager.message_check = my_message_checker

Plugins
-------

Plugins are a simple way of extending your bot. They come in the form of classes containing
commands. All plugins are derived from :class:`.Plugin`.

.. code-block:: python3

    from curious.commands.plugin import Plugin

    class MyPlugin(Plugin):
        ...

Commands can be created with the usage of the :meth:`.command` decorator:

.. code-block:: python3

    from curious.commands.decorators import command
    from curious.commands.context import Context

    class MyPlugin(Plugin):
        @command()
        async def pong(self, ctx: Context):
            await ctx.channel.messages.send("Ping!")


You can register plugins or modules containing plugins with the manager:

.. code-block:: python3

    @bot.event("ready")
    async def load_plugins(ctx: EventContext):
        # load plugin explicitly
        await manager.load_plugin(PluginClass, arg1)
        # load plugins from a module
        await manager.load_plugins_from("my.plugin.module")

Commands
--------

Commands are a way of running an isolated block of code in response to a user sending a message
with a prefix. Commands can be created with the :meth:`~curious.commands.decorators.command`
decorator which will automatically annotate the function with some metadata that marks it as a
command.

.. code-block:: python3

    @command()
    async def ping(self, ctx: Context):
        await ctx.channel.messages.send("Pong!")

The command decorator takes several arguments to customize the behaviour of the command outside
of the code inside the function; see the decorator docstring for more information.

Subcommands
-----------

Curious supports subcommands natively, using a small amount of metaprogramming magic. To create a
subcommand, simply use the ``parent.subcommand()`` function as a decorator on your command, like so:

.. code-block:: python3

    @command()
    async def say(self, ctx: Context):
        # this only runs if no subcommand was provided by the user
        await ctx.channel.messages.send(":x: What do you want me to say?")

    @say.subcommand()
    async def hello(self, ctx: Context):
        await ctx.channel.messages.send("Hello!")

Subcommands can be nested infinitely deep; you can have subcommands of subcommands down to any
level.

Context
-------

.. warning::

    This is subject to change in newer versions due to ContextVar support.

The :class:`.Context` object is a powerful object when using commands; as well as containing some
internal machinery used to run commands it also provides an interface to the context of the
command, i.e. the server/channel/author for the command, and so on.

Some useful attributes on the context object:

    - :attr:`.Context.channel` - The :class:`.Channel` object that the command was sent in.
    - :attr:`.Context.author` - The :class:`.Member` or :class:`.User` that sent the command.
    - :attr:`.Context.guild` - The :class:`.Guild` object the command was sent in. May be None.
    - :attr:`.Context.bot` - The reference to the bot that the command was handled by.
    - :attr:`.Context.event_context` - The :class:`.EventContext` used internally for the command.

Arguments
---------

Arguments to commands are consumed in a specific way, according to the function signature:

 - Positional arguments are consumed from single words or single blocks of quoted words.
 - ``*args`` arguments consume every single word.
 - ``*, argument`` arguments also consume every single word.
 - Keyword arguments are consumed, but use their default value if not found.
 - ``**kwargs`` is ignored.

This means that a function with the signature ``(arg1, arg2, *, arg3)``, when fed the input of
``"test1 test2 test3 test4"`` would result in ``{arg1: test1, arg2: test2, arg3: test3 test4}``.

Additionally, arguments can be typed; this allows automatic conversion from the string input to
the appropriate type for your function. This is achieved through the usage of standard Python 3
type annotations on the arguments. Some built-in converters are provided:

 - ``arg: int`` - converts the argument into an integer.
 - ``arg: float`` - converts the argument into a float.
 - ``arg: Channel`` - converts the argument into a :class:`.Channel`.
 - ``arg: Member`` - converts the argument into a :class:`.Member`.

Additional converters can be added by calling :meth:`.Context.add_converter`; the converter must
be a simple callable that takes a pair of arguments ``(ctx, arg)`` and returns the appropriate type.

Conditions
----------

Conditions are a way to ensure that a command only runs under certain circumstances. A condition
can be added to a command with the usage of the :meth:`.condition` decorator:

.. code-block:: python3

    @command()
    @condition(lambda ctx: ctx.guild.id == 198101180180594688)
    async def secret_command(self, ctx): ...

The argument to ``condition`` must be a callable that takes one argument, a :class:`.Context`
object, and returns True if the command will run and False otherwise. If an exception is raised,
it will be trapped and the command will not run (similar to returning False).

Free-standing commands
----------------------

You can also add free-standing commands that aren't bound to a plugin with
:meth:`.CommandsManager.add_command`:

.. code-block:: python3

    @command()
    async def ping(ctx: Context):
        await ctx.channel.send(content="Pong!")

    manager.add_command(ping)

These will then be available to the client.

Background Tasks
----------------

Background tasks are async functions that run in the background; i.e. you don't have to await
them. curious provides an easy, portable way to spawn a background task from a :class:`.Plugin`,
using :meth:`.Plugin.spawn`:

.. code-block:: python3

    async def my_task(self):
        while True:
            print("Ok!")
            await trio.sleep(300)

    @command()
    async def spawn(self, ctx):
        await self.spawn(self.my_task)

This task will be parented to the plugin's task group, which is parented to the client's root
task group. Exceptions will automatically be swallowed and logged, to prevent crashing the whole
bot.