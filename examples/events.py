"""
An example bot that uses events.
"""

# Events are the main way of listening to things that happen to the bot.
# They are registered with the @bot.event("name") decorator, or just the @event() decorator
# inside of plugins.

# Let's create a simple plugin that logs all messages, and another event that announces bans.

# First, the required imports
from curious.commands import CommandsManager
from curious.commands.plugin import Plugin
from curious.core.client import Client
from curious.core.event import EventContext, event
from curious.dataclasses.guild import Guild
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message


class BasicPlugin(Plugin):
    # We use the decorator to designate what event we wish to listen to.
    @event("message_create")
    # Events take at least one param - the EventContext. This contains our shard ID, as well as the
    # bot instance.
    async def log_message(self, ctx: EventContext, message: Message):
        # `log_message` takes a Message as its second argument, because it's a `message_create`
        # event.
        # Let's log the message content and author:
        print("Message recieved: `{}` from `{}`".format(message.content, message.author.user.name))
        # Let's also log the guild, if there is a guild.
        if message.guild is not None:
            print("Guild: {}".format(message.guild.name))
        # Finally, log the shard ID.
        print("Shard: {}".format(ctx.shard_id))


# Create the commands bot instance.
bot = Client()
manager = CommandsManager(client=bot, command_prefix="!")


# Add our plugin.
@bot.event("ready")
async def ready(ctx: EventContext):
    await manager.load_plugin(BasicPlugin)


# Now, we add the ban announcement event.
@bot.event("member_ban")
async def announce_ban(ctx: EventContext, guild: Guild, member: Member):
    # Send the ban message to the system channel.
    await guild.system_channel.messages.send("{} got bent".format(member.user.name))


# Now, all that is left is to run the bot.
bot.run('MjYwOTUwODE2NTM2NTI2ODQ5.Cz2mGQ.SKl78a6NT6SBpwYQrIDnR1olPqo')
