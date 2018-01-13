"""
An example bot that uses Curious' commands.
"""

# Required imports!
# You have to import the Client (to create the bot) and the Plugin class (to create a plugin).
from curious.commands import CommandsManager, command, condition
from curious.commands.context import Context
from curious.commands.plugin import Plugin
from curious.core.client import Client
from curious.core.event import EventContext


# Plugins are defined as types that inherit from ``Plugin``.
# You can inherit from any other class, but you MUST inherit from Plugin as well.
class Core(Plugin):
    # To define a command, you decorate a regular function with a `command()` decorator.
    # This will mark the function as a command that can be ran inside Discord.

    # The default name for the command will be the same as the function name. You can override
    # this by passing `name=` as a keyword argument to the decorator.
    @command()
    # All commands take a single parameter by default, `ctx`. This is the context which contains
    # useful attributes such as the channel or the guild the command was received on.
    async def ping(self, ctx: Context):
        """
        Responds to a user with `Pong!`.
        """
        # The docstring above is the default help text for the command.
        # We can get the member by using `ctx.author` parameter.
        member = ctx.author
        # To send a message back to the channel, you must use `ctx.channel.send(...)`.
        # We use `member.mention` here to mention the person that pinged us.
        await ctx.channel.messages.send("{}, pong!".format(member.mention))

    # Commands can also take parameters. They are defined by the function signature of the function.
    @command()
    async def hello(self, ctx: Context, name: str):
        """
        Says hello to somebody.
        """
        # The `name` in our signature allows somebody to run `!hello world` and `name` will be
        # automatically replaced with the string `world`.
        await ctx.channel.messages.send("Hello, {}!".format(name))

    # Commands can also provide aliases, by passing in a list.
    @command(aliases=["cold"])
    async def cool(self, ctx: Context):
        """
        Tells if the user is cool or not.
        """
        await ctx.channel.messages.send("It's a bit chilly.")

    # You can also provide invokation checks - these prevent people from running it unless they
    # meet specific criteria.
    @command()
    @condition(lambda ctx: "e" not in ctx.author.nickname)
    async def a(self, ctx: Context):
        """
        Only users without an `e` in their nickname can run this command.
        """
        await ctx.channel.messages.send("The letter `e` is for nerds!")


# To tie this all together, a new client instance needs to be created, and a manager created.
# The command_prefix argument tells us what prefix should be used to invoke commands.
bot = Client()
manager = CommandsManager(client=bot, command_prefix="!")
manager.register_events()


# Add the Core class as a plugin to the bot, inside the ready event.
@bot.event("ready")
async def ready(ctx: EventContext):
    print("Logged in as", bot.user.name)
    await manager.load_plugin(Core)


# Run the bot with your token.
bot.run('MjYwOTUwODE2NTM2NTI2ODQ5.Cz2mGQ.SKl78a6NT6SBpwYQrIDnR1olPqo')
