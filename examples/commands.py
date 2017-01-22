"""
An example bot that uses Curious' commands.
"""

# Required imports!
# You have to import the CommandsBot (to create the bot) and the Plugin class (to create a plugin).
from curious.commands import command
from curious.commands.bot import CommandsBot
from curious.commands.context import Context
from curious.commands.plugin import Plugin


# Plugins are defined as types that inherit from ``Plugin``.
# You can inherit from any other class, but you MUST inherit from Plugin as well.
class Core(Plugin):
    # To define a command, you decorate a regular function with a `command()` decorator.
    # This will mark the function as a command that can be ran inside Discord.

    # The default name for the command will be the same as the function name. You can override this by passing
    # `name=` as a keyword argument to the decorator.
    @command()
    # All commands take a single parameter by default, `ctx`. This is the context which contains useful attributes
    # such as the channel or the guild the command was received on.
    async def ping(self, ctx: Context):
        """
        Responds to a user with `Pong!`.
        """
        # The docstring above is the default help text for the command.
        # We can get the member by using `ctx.author` parameter.
        member = ctx.author
        # To send a message back to the channel, you must use `ctx.channel.send(...)`.
        # We use `member.mention` here to mention the person that pinged us.
        await ctx.channel.send("{}, pong!".format(member.mention))

    # Commands can also take parameters. They are defined by the function signature of the function.
    @command()
    async def hello(self, ctx: Context, name: str):
        """
        Says hello to somebody.
        """
        # The `name` in our signature allows somebody to run `!hello world` and `name` will be automatically replaced
        #  with the string `world`.
        await ctx.channel.send("Hello, {}!".format(name))

    # Commands can also provide aliases, by passing in a list.
    @command(aliases=["cold"])
    async def cool(self, ctx: Context):
        """
        Tells if the user is cool or not.
        """
        await ctx.channel.send("It's a bit chilly.")

    # You can also provide invokation checks - these prevent people from running it unless they meet specific criteria.
    @command(invokation_checks=[lambda ctx: "e" not in ctx.author.user.nickname])
    async def a(self, ctx: Context):
        """
        Only users without an `e` in their nickname can run this command.
        """
        await ctx.channel.send("The letter `e` is for nerds!")


# To tie this all together, a new CommandsBot instance needs to be created.
# The command_prefix argument tells us what prefix should be used to invoke commands.
bot = CommandsBot(command_prefix="!")

# Add the Core class as a plugin to the bot.
Core.setup(bot)

# Run the bot with your token.
bot.run('token')
