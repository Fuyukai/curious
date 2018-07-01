"""
Commonly used conditions.

.. currentmodule:: curious.commands.conditions
"""

from curious.commands import Context, condition


def is_owner():
    """
    A :func:`.condition` that ensures the author of the message is the owner of the bot.

    The owner is checked automatically by using the application info of the bot.

    Example::

        @command()
        @is_owner()
        async def kill(ctx: Context):
            await ctx.bot.kill()
    """

    def _condition(ctx: Context):
        # If the application info request has not been completed
        # yet we cannot guarantee the command could be ran.
        if ctx.bot.application_info is None:
            return False

        owner = ctx.bot.application_info.owner
        return ctx.message.author_id == owner.id

    return condition(_condition)


def author_has_permissions(bypass_owner: bool = True, **permissions):
    """
    A :func:`.condition` that ensures the author of the
    message has all of the specified permissions.

    Example::

        @command()
        @author_has_permissions(kick_members=True)
        async def kick(ctx: Context, member: Member):
            await member.kick()
            await ctx.channel.messages.send(':wave:')

    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    :param permissions: A mapping of permissions to check.
    """

    def _condition(ctx: Context):
        perms = ctx.channel.effective_permissions(ctx.author)
        return all(getattr(perms, name, None) is value
                   for name, value in permissions.items())

    return condition(_condition, bypass_owner=bypass_owner)


def bot_has_permissions(bypass_owner: bool = False, **permissions):
    """
    A :func:`.condition` that ensures the bot
    has all of the specified permissions.

    Example::

        @command()
        @bot_has_permissions(send_messages=True)
        async def test(ctx: Context):
            await ctx.channel.messages.send('The bot can send messages.')

    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    :param permissions: A mapping of permissions to check.
    """

    def _condition(ctx: Context):
        perms = ctx.channel.me_permissions
        return all(getattr(perms, name, None) is value
                   for name, value in permissions.items())

    return condition(_condition, bypass_owner=bypass_owner)


author_has_perms = author_has_permissions
bot_has_perms = bot_has_permissions


def author_has_roles(*roles: str, bypass_owner: bool = True):
    """
    A :func:`.condition` that ensures the author of the message has all of the specified roles.

    The role names must all be exact matches.

    Example::

        @command()
        @author_has_roles('Cool')
        async def cool(ctx: Context):
            await ctx.channel.messages.send('You are cool.')

    :param roles: A collection of role names.
    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    """

    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        author_roles = {role.name for role in ctx.author.roles}
        return all(role in author_roles for role in roles)

    return condition(_condition, bypass_owner=bypass_owner)


def bot_has_roles(*roles: str, bypass_owner: bool = False):
    """
    A :func:`.condition` that ensures the bot has all of the specified roles.

    The role names must all be exact matches.

    Example::

        @command()
        @bot_has_roles('Cool')
        async def cool(ctx: Context):
            await ctx.channel.messages.send('The bot is cool.')

    :param roles: A collection of role names.
    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    """

    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        bot_roles = {role.name for role in ctx.guild.me.roles}
        return all(role in bot_roles for role in roles)

    return condition(_condition, bypass_owner=bypass_owner)


def is_guild_owner(bypass_owner: bool = True):
    """
    A :func:`.condition` that ensures the author of the message is also the owner of the guild.

    Example::

        @command()
        @is_guild_owner()
        async def test(ctx: Context):
            await ctx.channel.messages.send('You are the owner of this guild.')

    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    """

    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        return ctx.message.author_id == ctx.guild.owner_id

    return condition(_condition, bypass_owner=bypass_owner)
