"""
The main client class.

This contains a definition for :class:`.Client` which is used to interface primarily with Discord.

.. currentmodule:: curious.core.client
"""

import enum
import importlib
import inspect
import logging
import re
import sys
import traceback

import collections
import curio
import multidict
import typing
from cuiows.exc import WebsocketClosedError
from curio.task import Task

from curious.commands import cmd, context, plugin
from curious.core.event import EventContext, event as ev_dec
from curious.dataclasses import guild as dt_guild
from curious.dataclasses.appinfo import AppInfo
from curious.dataclasses.invite import Invite
from curious.dataclasses.message import Message
from curious.dataclasses.status import Game, Status
from curious.dataclasses.user import BotUser, User
from curious.dataclasses.webhook import Webhook
from curious.dataclasses.widget import Widget
from curious.exc import CuriousError
from curious.http.httpclient import HTTPClient
from curious.util import attrdict, base64ify

#: A sentinel value to indicate that the client should automatically shard.
AUTOSHARD = object()


class BotType(enum.IntEnum):
    """
    An enum that signifies what type of bot this bot is.
    
    This will tell the commands handling how to respond, as well as how to log in.
    """
    #: Regular bot. This signifies that the client should log in as a bot account.
    BOT = 1

    #: User bot. This signifies that the client should log in as a user account.
    USERBOT = 2

    # 4 is reserved

    #: No bot responses. This signifies that the client should respond to ONLY USER messages.
    ONLY_USER = 8

    #: No DMs. This signifies the bot only works in guilds.
    NO_DMS = 16

    #: No guilds. This signifies the bot only works in DMs.
    NO_GUILDS = 32

    #: Self bot. This signifies the bot only responds to itself.
    SELF_BOT = 64


def split_message_content(content: str, delim: str = " ") -> typing.List[str]:
    """
    Splits a message into individual parts by `delim`, returning a list of strings.
    This method preserves quotes.
    
    .. code-block:: python
    
        content = '!send "Fuyukai desu" "Hello, world!"'
        split = split_message_content(content, delim=" ")

    :param content: The message content to split.
    :param delim: The delimiter to split on.
    :return: A list of items split
    """

    def replacer(m):
        return m.group(0).replace(delim, "\x00")

    parts = re.sub(r'".+?"', replacer, content).split()
    parts = [p.replace("\x00", " ") for p in parts]
    return parts


def prefix_check_factory(prefix: typing.Union[str, typing.Iterable[str]]):
    """
    The default message function factory.
    
    This provides a callable that will fire a command if the message begins with the specified prefix or list of 
    prefixes.
    
    If ``command_prefix`` is provided to the :class:`.Client`, then it will automatically call this function to get a 
    message check function to use.
    
    .. code-block:: python
        
        # verbose form
        message_check = prefix_check_factory(["!", "?"])
        cl = Client(message_check=message_check)
        
        # implicit form
        cl = Client(command_prefix=["!", "?"])
        
    The :attr:`prefix` is set on the returned function that can be used to retrieve the prefixes defined to create 
    the function at any time.
    
    :param prefix: A :class:`str` or :class:`typing.Iterable[str]` that represents the prefix(es) to use. 
    :return: A callable that can be used for the ``message_check`` function on the client.
    """

    def __inner(bot: Client, message):
        matched = None
        if isinstance(prefix, str):
            match = message.content.startswith(prefix)
            if match:
                matched = prefix

        elif isinstance(prefix, collections.Iterable):
            for i in prefix:
                if message.content.startswith(i):
                    matched = i
                    break

        if not matched:
            return None

        tokens = split_message_content(message.content[len(matched):])
        command_word = tokens[0]

        return command_word, tokens[1:], matched

    __inner.prefix = prefix
    return __inner


class Client(object):
    """
    The main client class. This is used to interact with Discord.

    When creating a client object, you can either pass a token explicitly, or pass in in the :meth:`start` call or
    similar.

    .. code:: python

        bot = Client("'a'")  # pass explicitly
        bot.run("'b'")  # or pass to the run call.

    """

    def __init__(self, token: str = None, *,
                 enable_commands: bool = True,
                 command_prefix: typing.Union[str, list] = None,
                 message_check=None,
                 description: str = "The default curious description",
                 state_klass: type = None,
                 bot_type: int = (BotType.BOT | BotType.ONLY_USER)):
        """
        :param token: The current token for this bot.  
            This can be passed as None and can be initialized later.
            
        :param enable_commands: Should commands integration be enabled?  
            If this is False, commands can still be registered etc, they just won't fire (the event won't appear).
        
        :param command_prefix: The command prefix for this bot.
        :param message_check: The message check function for this bot.  
        
            This should take two arguments, the client and message, and should return either None or a 3-item tuple:
              - The command word matched
              - The tokens after the command word
              - The prefix that was matched.
              
        :param description: The description of this bot for usage in the default help command.
            
        :param state_klass: The class to construct the connection state from.
        
        :param bot_type: A union of :class:`~.BotType` that defines the type of this bot.
        """
        #: The mapping of `shard_id -> gateway` objects.
        self._gateways = {}  # type: typing.Dict[int, Gateway]

        #: The number of shards this client has.
        self.shard_count = 0

        #: The token for the bot.
        self._token = token

        if state_klass is None:
            from curious.core.state import State
            state_klass = State

        #: The current connection state for the bot.
        self.state = state_klass(self)

        #: The bot type for this bot.
        self.bot_type = bot_type

        if self.bot_type & BotType.BOT and self.bot_type & BotType.USERBOT:
            raise ValueError("Bot cannot be a bot and a userbot at the same time")

        #: The current event storage.
        self.events = multidict.MultiDict()

        #: The current "temporary" listener storage.
        #: Temporary listeners are events that listen, and if they return True the listener is remove.
        #: They are used in the HTTP method by `wait=`, for example.
        self._temporary_listeners = multidict.MultiDict()

        #: The :class:`~.HTTPClient` used for this bot.
        self.http = None  # type: HTTPClient

        #: The cached gateway URL.
        self._gw_url = None  # type: str

        #: The application info for this bot.
        #: Instance of :class:`~.AppInfo`.
        #: This will be None for user bots.
        self.application_info = None  # type: AppInfo

        #: The logger for this bot.
        self._logger = logging.getLogger("curious.client")

        if enable_commands:
            if not command_prefix and not message_check:
                raise TypeError("Must provide one of `command_prefix` or `message_check`")

            self._message_check = message_check or prefix_check_factory(command_prefix)
        else:
            self._message_check = lambda x: None

        #: The description of this bot.
        self.description = description

        #: The dictionary of command objects to use.
        self.commands = attrdict()

        #: The dictionary of plugins to use.
        self.plugins = {}

        self._plugin_modules = {}

        if enable_commands:
            # Add the handle_commands as a message_create event.
            self.add_event(self.handle_commands)
            self.add_event(self.default_command_error)

            from curious.commands.plugin_core import _Core
            self.add_plugin(_Core(self))

        self.scan_events()

    @property
    def user(self) -> BotUser:
        """
        :return: The :class:`~.User` that this client is logged in as.
        """
        return self.state._user

    @property
    def guilds(self) -> 'typing.Mapping[int, dt_guild.Guild]':
        """
        :return: A mapping of int -> :class:`~.Guild` that this client can see.
        """
        return self.state.guilds

    @property
    def invite_url(self):
        """
        :return: The invite URL for this bot.
        """
        return "https://discordapp.com/oauth2/authorize?client_id={}&scope=bot".format(self.application_info.client_id)

    @property
    def events_handled(self) -> collections.Counter:
        """
        A :class:`collections.Counter` of all events that have been handled since the bot's bootup.
        This can be used to track statistics for events.
         
        .. code-block:: python
        
            @command()
            async def events(self, ctx: Context):
                '''
                Shows the most common events.
                '''
                
                ev = ctx.bot.events_handled.most_common(3)
                await ctx.channel.send(", ".join("{}: {}".format(*x) for x in ev)
        
        """

        c = collections.Counter()
        for gw in self._gateways.values():
            c.update(gw._dispatches_handled)

        return c

    def find_channel(self, channel_id: int):
        """
        Finds a channel by channel ID.
        """
        return self.state.find_channel(channel_id)

    async def get_gateway_url(self):
        if self._gw_url:
            return self._gw_url

        self._gw_url = await self.http.get_gateway_url()
        return self._gw_url

    async def get_shard_count(self):
        gw, shards = await self.http.get_shard_count()
        self._gw_url = gw

        return shards

    def guilds_for(self, shard_id: int) -> 'typing.Iterable[dt_guild.Guild]':
        """
        Gets the guilds for this shard.

        :param shard_id: The shard ID to get guilds from.
        :return: A list of :class:`Guild` that client can see on the specified shard.
        """
        return self.state.guilds_for_shard(shard_id)

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
            name = func.event

        self.events.add(name, func)

    def add_listener(self, name: str, func):
        """
        Adds a temporary listener.

        :param name: The name of the event to listen under.
        :param func: The callable to call.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Listener must be a coroutine function")

        self._temporary_listeners.add(name, func)

    def remove_event(self, name: str, func):
        """
        Removes a function event.

        :param name: The name the event is registered under/.
        :param func: The function to remove.
        """
        a = self.events.getall(name)
        if func in a:
            a.remove(func)

        self.events.pop(name)
        for item in a:
            self.events.add(name, item)

    def event(self, name: str):
        """
        A convenience decorator to mark a function as an event.

        This will copy it to the events dictionary, where it will be used as an event later on.

        .. code-block:: python
        
            @bot.event("message_create")
            async def something(ctx, message: Message):
                pass
                

        :param name: The name of the event.
        """

        def _inner(func):
            f = ev_dec(name)(func)
            self.add_event(func=f)

        return _inner

    def scan_events(self):
        """
        Scans this class for functions marked with an event decorator.
        """
        for _, item in inspect.getmembers(self, predicate=lambda x: hasattr(x, "event") and getattr(x, "scan", False)):
            self._logger.info("Registering event function {} for event {}".format(_, item.event))
            self.add_event(item)

    async def _error_wrapper(self, func, *args, **kwargs):
        try:
            await func(*args, **kwargs)
        except Exception as e:
            self._logger.exception("Unhandled exception in {}!".format(func.__name__))

    async def _wrap_context(self, ctx: 'context.Context'):
        """
        Wraps a context in a safety wrapper.

        This will dispatch `command_exception` when an error happens.
        """
        try:
            await ctx.invoke()
        except Exception as e:
            gw = self._gateways[ctx.event_context.shard_id]
            await self.fire_event("command_error", e, ctx=ctx, gateway=gw)

    async def _temporary_wrapper(self, event, listener, *args, **kwargs):
        try:
            result = await listener(*args, **kwargs)
        except Exception as e:
            self._logger.exception("Unhandled exception in {}!".format(listener.__name__))
            return
        if result is True:
            # Complex removal bullshit
            try:
                items = self._temporary_listeners.getall(event)
            except KeyError:
                # early removal done already, ignore
                return

            try:
                items.remove(listener)
            except ValueError:
                # race condition bullshit
                return
            # remove all keys
            self._temporary_listeners.pop(event)

            for i in items:
                # re-add all new items
                self._temporary_listeners.add(event, i)

    def remove_listener_early(self, event, listener):
        """
        Removes a listener early.

        :param event: The event to remove from.
        :param listener: The listener to remove.
        """
        all = self._temporary_listeners.getall(event)
        if listener in all:
            all.remove(listener)

        self._temporary_listeners.pop(event)
        for i in all:
            self._temporary_listeners.add(event, i)

    async def fire_event(self, event_name: str, *args, **kwargs) -> typing.List[Task]:
        """
        Fires an event to run.

        This will wrap the events in Tasks and return a list of them.

        :param event_name: The event name to fire.
        :return: A :class:`list` of :class:`curio.task.Task` representing the events.
        """
        gateway = kwargs.pop("gateway")

        if not self.state.is_ready(gateway.shard_id).is_set() and event_name != "connect":
            return

        coros = self.events.getall(event_name, [])

        temporary_listeners = self._temporary_listeners.getall(event_name, [])

        if not coros and not temporary_listeners:
            return

        self._logger.debug(
            "Dispatching event {} to {} listeners"
            " on shard {}".format(event_name, len(coros) + len(temporary_listeners), gateway.shard_id)
        )

        if "ctx" not in kwargs:
            ctx = EventContext(self, gateway.shard_id, event_name)
        else:
            ctx = kwargs.pop("ctx")

        tasks = []
        for event in coros.copy():
            tasks.append(await curio.spawn(self._error_wrapper(event, ctx, *args, **kwargs), daemon=True))

        for listener in temporary_listeners:
            tasks.append(await curio.spawn(self._temporary_wrapper(event_name, listener, ctx, *args, **kwargs),
                                           daemon=True))

        return tasks

    # commands
    @ev_dec("command_error", scan=False)
    async def default_command_error(self, ctx, e):
        """
        Default error handler.

        This is meant to be overriden - normally it will just print the traceback.
        """
        if len(self.events.getall("command_error")) >= 2:
            # remove ourselves
            self.remove_event("command_error", self.default_command_error)
            return

        traceback.print_exception(None, e, e.__traceback__)

    @ev_dec("message_create", scan=False)
    async def handle_commands(self, event_ctx: EventContext, message: Message):
        """
        Handles invokation of commands.

        This is added as an event during initialization.
        """
        # oddities
        if message.author is None:
            self._logger.warning("Got None author...")
            return

        user = message.author.user if hasattr(message.author, "user") else message.author

        # check for bot type
        if self.bot_type & BotType.SELF_BOT and user != self.user:
            return

        if self.bot_type & BotType.NO_DMS and message.channel.is_private:
            return

        if self.bot_type & BotType.NO_GUILDS and message.channel.guild_id is not None:
            return

        if self.bot_type & BotType.ONLY_USER and user.bot:
            return

        if not message.content:
            # Minor optimization - don't fire on empty messages.
            return

        # use the message check function
        _ = self._message_check(self, message)
        if inspect.isawaitable(_):
            _ = await _

        if not _:
            # not a command, do not bother
            return

        # func should return command_word and args for the command
        command_word, args, prefix = _
        command = self.get_command(command_word)
        if command is None:
            return

        # Create the context object that will be passed in.
        ctx = context.Context(self, command=command, message=message,
                              event_ctx=event_ctx)
        ctx.prefix = prefix
        ctx.name = command_word
        ctx.raw_args = args

        await curio.spawn(self._wrap_context(ctx))

    def add_command(self, command_name: str, command: 'cmd.Command'):
        """
        Adds a command to the internal registry of commands.

        :param command_name: The name of the command to add.
        :param command: The command object to add.
        """
        if command_name in self.commands:
            if not self.commands[command_name]._overridable:
                raise ValueError("Command {} already exists".format(command_name))
            else:
                self.commands.pop(command_name)

        self.commands[command_name] = command

    def add_plugin(self, plugin_class):
        """
        Adds a plugin to the bot.

        :param plugin_class: The plugin class to add.
        """
        events, commands = plugin_class._scan_body()

        for event in events:
            event.plugin = plugin_class
            self.events.add(event.event, event)

        for command in commands:
            # Bind the command to the plugin.
            command.instance = plugin_class
            # dont add any aliases
            self.add_command(command.name, command)

        self.plugins[plugin_class.name] = plugin_class

    async def load_plugins_from(self, import_name: str, *args, **kwargs):
        """
        Loads a plugin and adds it to the internal registry.

        :param import_name: The import name of the plugin to add (e.g `bot.plugins.moderation`).
        """
        module = importlib.import_module(import_name)
        mod = [module, []]

        # Locate all of the Plugin types.
        for name, member in inspect.getmembers(module):
            if not isinstance(member, type):
                # We only want to inspect instances of type (i.e classes).
                continue

            inherits = inspect.getmro(member)
            # remove `member` from the mro
            # this prevents us registering Plugin as a plugin
            inherits = [i for i in inherits if i != member]
            if plugin.Plugin not in inherits:
                # Only inspect instances of plugin.
                continue

            if not hasattr(member, "__dict__"):
                # don't be difficult
                continue

            # evil cpython type implementation detail abuse
            if member.__dict__.get("_include_in_scan", True) is False:
                # this won't show up for subclasses.
                # so they always have to be explicitly set
                continue

            # Assume it has a setup method on it.
            result = member.setup(self, *args, **kwargs)
            if inspect.isawaitable(result):
                result = await result

            # Add it to the list of plugins we need to destroy when unloading.
            # We add the type, not the instance, as the instances are destroyed separately.
            mod[1].append(member)

        if len(mod[1]) == 0:
            raise ValueError("Plugin contained no plugin classes (classes that inherit from Plugin)")

        self._plugin_modules[import_name] = mod

    async def unload_plugins_from(self, import_name: str):
        """
        Unloads plugins from the specified import name.

        This is the opposite to :meth:`load_plugins_from`.
        """
        mod, plugins = self._plugin_modules[import_name]
        # we can't do anything with the module currently because it's still in our locals scope
        # so we have to wait to delete it
        # i'm not sure this is how python imports work but better to be safe
        # (especially w/ custom importers)

        for plugin in plugins:
            # find all the Command instances with this plugin as the body
            for name, command in self.commands.copy().items():
                # isinstance() checks ensures that the type of the instance is this plugin
                if isinstance(command.instance, plugin):
                    # make sure the instance isn't lingering around
                    command.instance = None
                    # rip
                    self.commands.pop(name)

            # remove all events registered
            for name, event in self.events.copy().items():
                # not a plugin event
                if not hasattr(event, "plugin"):
                    continue
                if isinstance(event.plugin, plugin):
                    event.plugins = None
                    self.remove_event(name, event)

            # now that all commands are dead, call `unload()` on all of the instances
            for name, instance in self.plugins.copy().items():
                if isinstance(instance, plugin):
                    r = instance.unload()
                    if inspect.isawaitable(r):
                        await r

                    self.plugins.pop(name)

        # remove from sys.modules and our own registry to remove all references
        del sys.modules[import_name]
        del self._plugin_modules[import_name]
        del mod

    def get_commands_for(self, plugin: 'plugin.Plugin') -> typing.Generator['cmd.Command', None, None]:
        """
        Gets the commands for the specified plugin.

        :param plugin: The plugin instance to get commands of.
        :return: A list of :class:`Command`.
        """
        for command in self.commands.copy().values():
            if command.instance == plugin:
                yield command

    def get_command(self, command_name: str) -> 'typing.Union[cmd.Command, None]':
        """
        Gets a command object for the specified command name.

        :param command_name: The name of the command.
        :return: The command object if found, otherwise None.
        """

        def _f(cmd: cmd.Command):
            return cmd.can_be_invoked_by(command_name)

        f = filter(_f, self.commands.values())
        return next(f, None)

    # Gateway functions
    async def change_status(self, game: Game = None, status: Status = Status.ONLINE, afk: bool = False,
                            shard_id: int = 0):
        """
        Changes the bot's current status.

        :param game: The game object to use. None for no game.
        :param status: The new status. Must be a :class:`Status` object.
        :param afk: Is the bot AFK? Only useful for userbots.
        :param shard_id: The shard to change your status on.
        """
        gateway = self._gateways[shard_id]
        return await gateway.send_status(game, status, afk=afk)

    async def wait_for(self, event_name: str, predicate: typing.Callable = None):
        """
        Wait for an event to happen in the gateway.

        You can specify a check to happen to check if this event is the one to return.
        When the check returns True, the listener is removed and the event data is returned.
        For example, to wait for a message with the content `Heck`:

        .. code:: python

            message = await client.wait_for("message_create", predicate=lambda m: m.content == "Heck")

        You can pass any function to this predicate. If this function takes an error, it will remove the listener,
        then raise into your code.

        .. code:: python

            async def _closure(message):
                if message.author.id != 66237334693085184:
                    return False

                if message.content == "sparkling water > tap water":
                    return True

                return False

            wrong = await client.wait_for("message_create", predicate=_closure)

        :param event_name: The name of the event to wait for.
        :param predicate: An optional check function to return.
        :return: The result of the event.
        """
        if predicate is None:
            predicate = lambda *args, **kwargs: True

        event = curio.Event()
        result = None
        _exc = None

        async def __event_listener_inner(ctx: EventContext, *args, **kwargs):
            try:
                is_result = predicate(*args, **kwargs)
                if inspect.isawaitable(is_result):
                    is_result = await is_result
            except Exception as e:
                # It is NOT the result we want.
                nonlocal _exc
                _exc = e
                await event.set()
                # Return True so this listener dies.
                return True
            else:
                if is_result:
                    # It is the result we want, so set the event.
                    await event.set()
                    # Then we store the result.
                    nonlocal result
                    result = args  # TODO: Figure out keyword arguments
                    return True

                return False

        self.add_listener(event_name, __event_listener_inner)
        # Wait on the event to be set.
        try:
            await event.wait()
        except curio.CancelledError:
            # remove the listener
            self.remove_listener_early(event_name, __event_listener_inner)
            raise
        # If it's an exception, raise the exception.
        if _exc is not None:
            raise _exc
        # Otherwise, return the event result.
        return result

    # HTTP Functions
    async def edit_profile(self, *,
                           username: str = None,
                           avatar: bytes = None,
                           password: str = None):
        """
        Edits the profile of this bot.

        The user is **not** edited in-place - instead, you must wait for the `USER_UPDATE` event to be fired on the
        websocket.

        :param username: The new username of the bot.
        :param avatar: The bytes-like object that represents the new avatar you wish to use.
        :param password: The password to use. Only for user accounts.
        """
        if not self.user.bot and password is None:
            raise ValueError("Password must be passed for user bots")

        if username:
            if not 2 <= len(username) <= 32:
                raise ValueError("Username must be 2-32 characters")

        if avatar:
            avatar = base64ify(avatar)

        await self.http.edit_profile(username, avatar, password)

    async def edit_avatar(self, path: str):
        """
        A higher-level way to change your avatar.
        This allows you to provide a path to the avatar file instead of having to read it in manually.

        :param path: The path-like object to the avatar file.
        """
        with open(path, 'rb') as f:
            await self.edit_profile(avatar=f.read())

    async def get_user(self, user_id: int) -> User:
        """
        Gets a user by ID.

        :param user_id: The ID of the user to get.
        :return: A new User object.
        """
        try:
            return self.state._users[user_id]
        except KeyError:
            u = self.state.make_user(await self.http.get_user(user_id))
            # decache it if we need to
            self.state._check_decache_user(u.id)
            return u

    async def get_application(self, application_id: int) -> AppInfo:
        """
        Gets an application by ID.

        :param application_id: The client ID of the application to fetch.
        :return: A new :class:`AppInfo` object corresponding to the application.
        """
        data = await self.http.get_app_info(application_id=application_id)
        appinfo = AppInfo(self, **data)

        return appinfo

    async def get_webhook(self, webhook_id: int) -> Webhook:
        """
        Gets a webhook by ID.

        :param webhook_id: The ID of the webhook to get.
        :return: A new Webhook object.
        """
        return self.state.make_webhook(await self.http.get_webhook(webhook_id))

    async def get_invite(self, invite_code: str) -> Invite:
        """
        Gets an invite by code.

        :param invite_code: The invite code to get.
        :return: A new Invite object.
        """
        return Invite(self, **(await self.http.get_invite(invite_code)))

    async def get_widget(self, guild_id: int) -> Widget:
        """
        Gets a widget from a guild.
        
        :param guild_id: The ID of the guild to get the widget of. 
        :return: A :class:`Widget` object.
        """
        data = await self.http.get_widget_data(guild_id)
        return Widget(self, **data)

    # Utility functions
    async def connect(self, token: str = None, shard_id: int = 1):
        """
        Connects the bot to the gateway.

        This will NOT poll for events - only open a websocket connection!
        """
        from curious.core.gateway import Gateway

        if token:
            self._token = token

        if not self.http:
            self.http = HTTPClient(self._token, bot=bool(self.bot_type & BotType.BOT))

        if not self.application_info and self.bot_type & BotType.BOT:
            self.application_info = AppInfo(self, **(await self.http.get_app_info(None)))

        gateway_url = await self.get_gateway_url()
        self._gateways[shard_id] = await Gateway.from_token(self._token, self.state, gateway_url,
                                                            shard_id=shard_id, shard_count=self.shard_count)
        await self._gateways[shard_id].websocket.wait_for_ready()

        return self

    async def poll(self, shard_id: int):
        """
        Polls the gateway for the next event.

        :param shard_id: The shard ID of the gateway to shard.
        """
        from curious.core.gateway import ReconnectWebsocket
        gw = self._gateways[shard_id]
        while True:
            try:
                await gw.next_event()
            except WebsocketClosedError as e:
                # Try and handle the close.
                if e.reason == "Client closed connection":
                    # internal
                    return

                if e.code in [1000, 4007] or gw.session_id is None:
                    self._logger.info("Shard {} disconnected with code {}, creating new session".format(shard_id,
                                                                                                        e.code))
                    self.state._reset(gw.shard_id)
                    await gw.reconnect(resume=False)
                elif e.code not in (4004, 4011):
                    # Try and RESUME.
                    self._logger.info("Shard {} disconnected with close code {}, reason {}, "
                                      "attempting a reconnect.".format(shard_id, e.code, e.reason))
                    await gw.reconnect(resume=True)
                else:
                    raise
            except ReconnectWebsocket:
                # We've been told to reconnect, try and RESUME.
                await gw.reconnect(resume=True)

    async def boot_shard(self, shard_id: int, shard_count: int = None) -> curio.Task:
        """
        Boots a single gateway shard.
        
        This can be used to run multiple clients instead of having a single client shard.
        
        :param shard_id: The shard ID to boot. 
        :param shard_count: The number of shards being created.
        :return: The :class:`curio.Task` that represents the polling loop.
        """
        if shard_count:
            self.shard_count = shard_count

        await self.connect(self._token, shard_id=shard_id)
        t = await curio.spawn(self.poll(shard_id))
        t.id = "shard-{}".format(shard_id)
        return t

    async def start(self, shards: int = 1):
        """
        Starts the gateway polling loop.

        This is a convenience method that polls on all the shards at once.
        This will **only reboot safely returned shards.** Erroring shards won't be rebooted.
        """
        self._logger.info("Starting bot with {} shards.".format(shards))
        self.shard_count = shards
        tasks = []
        for shard_id in range(0, shards):
            await self.boot_shard(shard_id)
            self._logger.info("Sleeping for 5 seconds between shard creation.")
            await curio.sleep(5)

        wait = curio.wait(tasks)

        results = []

        # Wait for the next task.
        while True:
            task = await wait.next_done()  # type: curio.Task
            if task is None:
                break

            try:
                result = await task.join()
            except Exception as e:
                result = e
                self._logger.exception("Shard {} crashed, not rebooting it.".format(task.id))
            else:
                # reboot it
                self._logger.warning("Rebooting shard {}.".format(task.id))
                id = int(task.id.split("-")[1])
                t = await self.boot_shard(shard_id=id)
                wait.add_task(t)
            finally:
                results.append(result)

        return results

    async def start_autosharded(self, token: str = None):
        """
        Starts the bot with an automatically set number of shards.
        """
        if token:
            self._token = token

        if not self.http:
            # autosharded always means start autosharded
            self.http = HTTPClient(self._token, bot=True)

        shards = await self.get_shard_count()
        self.shard_count = shards
        await self.start(shards=shards)

    def run(self, token: str = None, shards: typing.Union[int, object] = 1):
        """
        Runs your bot with Curio with the monitor enabled.

        :param token: The token to run with.
        :param shards: The number of shards to run.
            If this is None, the bot will autoshard.
        """
        if token is not None:
            self._token = token

        if not self.bot_type & BotType.BOT and shards != 1:
            raise CuriousError("Cannot start user bots in sharded mode")

        try:
            kernel = curio.Kernel(with_monitor=True, warn_if_task_blocks_for=5)
        except TypeError:
            # old vers of curio
            kernel = curio.Kernel(with_monitor=True)
        if shards == AUTOSHARD:
            coro = self.start_autosharded(token)
        else:
            coro = self.start(shards=shards)

        try:
            return kernel.run(coro, shutdown=True)
        except (KeyboardInterrupt, EOFError):
            if kernel._crashed:
                self._logger.info("Kernel crashed, not cleaning up.")
                return
            self._logger.info("C-c/C-d received, killing bot. Waiting 5 seconds for all connections to close.")
            # Cleanup.
            coros = []
            for gateway in self._gateways.values():
                coros.append(gateway.websocket.close_now(1000, reason="Client closed connection"))
                coros.append(gateway._close())

            async def __cleanup():
                tasks = []
                for task in coros:
                    tasks.append(await curio.spawn(task))

                self._logger.info("Need to wait for {} task(s) to complete.".format(len(tasks)))

                # silence exceptions
                await curio.gather(tasks, return_exceptions=True)
                self._logger.info("Clean-up complete.")
                raise SystemExit()

            return kernel.run(__cleanup(), timeout=5)

    @classmethod
    def from_token(cls, token: str = None):
        """
        Starts a bot from a token object.

        :param token: The token to use for the bot.
        """
        bot = cls(token)
        return bot.run()
