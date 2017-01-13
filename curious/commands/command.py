import inspect
import typing

from curious.commands.context import Context
from curious.commands.exc import CheckFailureError, MissingArgumentError, CommandInvokeError, ConversionFailedError

# Default converters.
from curious.dataclasses import Channel
from curious.dataclasses.member import Member
from curious.util import replace_quotes


def convert_member(ctx: Context, arg: str):
    if arg.startswith("<@") and arg.endswith(">"):
        # Parse the mention out
        id = arg[2:-1]
        if id[0] == "!":  # nicknames
            id = id[1:]

        try:
            id = int(id)
        except ValueError:
            raise ConversionFailedError(ctx, arg, Member)

        member = ctx.guild.get_member(id)
        if not member:
            # todo: better error
            raise ConversionFailedError(ctx, arg, Member)
    else:
        member = ctx.guild.find_member(arg)
        if not member:
            raise ConversionFailedError(ctx, arg, Member)

    return member


def convert_channel(ctx: Context, arg: str):
    if arg.startswith("<#") and arg.endswith(">"):
        id = arg[2:-1]

        try:
            id = int(id)
        except ValueError:
            raise ConversionFailedError(ctx, arg, Channel)

        channel = ctx.guild.get_channel(id)
        if not channel:
            raise ConversionFailedError(ctx, arg, Channel)
    else:
        try:
            channel = next(filter(lambda c: c.name == arg, ctx.guild.channels), None)
            if channel is None:
                channel = next(filter(lambda c: c.id == int(arg), ctx.guild.channels))
        except (StopIteration, ValueError):
            raise ConversionFailedError(ctx, arg, Channel)

    return channel


converters = {
    int: lambda ctx, x: int(x),
    Member: convert_member,
    Channel: convert_channel
}


class Command(object):
    """
    A command object represents a command.
    """

    def __init__(self, cbl, *,
                 name: str = None, aliases: typing.List[str] = None,
                 invokation_checks: list = None):
        """
        :param cbl: The callable to use.
        :param name: The name of this command.
            If this isn't provided, it will be automatically determined from the callable name.

        :param aliases: A list of aliases that this command can be called as.
        """
        self.callable = cbl

        self.name = name
        if not self.name:
            # Use the __name__ of the callable instead
            # This isn't always accurate, but you should provide `name=` if you want that.
            self.name = self.callable.__name__

        self.aliases = [self.name] + (aliases if aliases else [])

        # Pre-calculate the function signature.
        # Saves a few MS every command in
        self._signature = inspect.signature(self.callable)

        #: The plugin instance to pass to this command.
        #: If this is None, it is assumed the command invoker does not need an instance.
        self._instance = None

        #: A list of invokation checks that must all return True before the underlying function is run.
        self.invokation_checks = invokation_checks if invokation_checks else []

    @property
    def instance(self):
        return self._instance

    @instance.setter
    def instance(self, value):
        if value is None:
            self._instance = None
            return

        # add the plugin_check func as a local check
        self.invokation_checks.append(value.plugin_check)
        self._instance = value

    def get_usage(self, ctx: Context, invoked_as: str) -> str:
        """
        :return: The usage text for this command.
        """
        final = ["{}{}".format(ctx.prefix, invoked_as)]

        for n, (name, param) in enumerate(self._signature.parameters.items()):
            # always skip the first arg
            if n == 0:
                continue

            if self.instance is not None:
                # skip the 2nd arg if we're bound to a plugin
                if n == 1:
                    continue

            # switch based on kind (again...)
            assert isinstance(param, inspect.Parameter)
            if param.kind in [inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY]:
                if param.annotation is not inspect.Parameter.empty:
                    s = "<{}: {}>".format(param.name, param.annotation.__name__)
                else:
                    s = "<{}>".format(param.name)

            elif param.kind in [inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_POSITIONAL]:
                if param.default is not inspect.Parameter.empty:
                    if param.annotation is not inspect.Parameter.empty:
                        s = "[{}: {} (default: {})]".format(param.name, param.annotation.__name__,
                                                            repr(param.default))
                    else:
                        s = "[{} (default: {})]".format(param.name, repr(param.default))
                else:
                    if param.annotation is not inspect.Parameter.empty:
                        s = "<{}: {}>".format(param.name, param.annotation.__name__ )
                    else:
                        s = "<{}>".format(param.name)
            else:
                s = ""

            final.append(s)

        return " ".join(final)

    def get_help(self, ctx: Context, invoked_as: str) -> str:
        """
        :return: The help text for this command.
        """
        doc = inspect.getdoc(self.callable)
        if not doc:
            return "This command has no help."
        else:
            return doc

    def _lookup_converter(self, thing, type_: type) -> typing.Callable[[Context, object], str]:
        """
        Gets a converter for the specified type.
        This is provided as a function for command subclasses to be able to override.
        """
        if thing is None:
            return lambda c, i: i
        return converters.get(type_, lambda ctx, x: str(x))

    async def _convert(self, ctx, *args):
        """
        Converts the arguments passed from discord into the function, based on it's type signature.
        """
        final_args = []
        final_kwargs = {}

        args_it = iter(args)

        for n, (name, param) in enumerate(self._signature.parameters.items()):
            if n == 0:
                # Don't convert the `self/ctx` argument.
                continue

            if self.instance is not None:
                if n == 1:
                    # Don't convert the bound `ctx` argument.
                    continue

            assert isinstance(param, inspect.Parameter)
            # We loop over the signature parameters because it's easier to use those to consume.
            # Get the next argument from args.
            try:
                arg = next(args_it)
            except StopIteration as e:
                # not good!
                # If we're a *arg format, we can safely handle this, or if we have a default.
                if param.kind == inspect.Parameter.VAR_POSITIONAL:
                    break

                if param.default is inspect.Parameter.empty:
                    raise MissingArgumentError(ctx, param.name) from e

                arg = param.default

            # Begin the consumption!
            if param.kind in [inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY]:
                # Only add it to the final_args, then continue the loop.
                arg = replace_quotes(arg)
                converter = self._lookup_converter(arg, param.annotation)
                final_args.append(converter(ctx, arg))
                continue

            if param.kind in [inspect.Parameter.KEYWORD_ONLY]:
                # Only add it to final_kwargs.
                # This is a consume all operation, so we eat all of the arguments.
                f = [arg]

                while True:
                    try:
                        next_arg = next(args_it)
                    except StopIteration:
                        break

                    f.append(next_arg)

                converter = self._lookup_converter(arg, param.annotation)
                if len(f) == 1:
                    final_kwargs[param.name] = converter(ctx, f[0])
                else:
                    final_kwargs[param.name] = converter(ctx, " ".join(f))
                continue

            if param.kind in [inspect.Parameter.VAR_POSITIONAL]:
                # This *shouldn't* be called on `*` arguments, but we can't be sure.
                # Special case - consume ALL the arguments.
                f = [arg]

                while True:
                    try:
                        next_arg = next(args_it)
                    except StopIteration:
                        break

                    f.append(next_arg)

                converter = self._lookup_converter(arg, param.annotation)
                final_args.append(converter(ctx, " ".join(f)))

                # We *could* get more arguments.
                # I mean, there's no more argument data to consume.
                # So if you haven't set a default, it won't show anything.
                # Continue anyway, though.
                continue

            if param.kind in [inspect.Parameter.VAR_KEYWORD]:
                # no
                continue

        return final_args, final_kwargs

    async def can_run(self, ctx: Context) -> typing.Tuple[int, typing.List[typing.Tuple[str, typing.Any]]]:
        """
        Checks if this command can run.

        This will return a two-item tuple: the number of checks that failed, the results of the checks.

        :param ctx: The command context.
        :return: The tuple described above.
        """
        failed, results = len(self.invokation_checks), []

        for check in self.invokation_checks:
            try:
                result = check(ctx)
                if inspect.isawaitable(result):
                    result = await result
            except CheckFailureError as e:
                result = repr(e)

            if not isinstance(result, CheckFailureError) and result:  # truthy value means succeeded
                failed -= 1

            results.append((check.__name__, result))

        return failed, results

    async def invoke(self, ctx: Context, *args):
        failed, _ = await self.can_run(ctx)
        if failed:
            raise CheckFailureError(ctx, _)

        final_args, final_kwargs = await self._convert(ctx, *args)

        try:
            if self.instance is not None:
                await self.callable(self.instance, ctx, *final_args, **final_kwargs)
            else:
                await self.callable(ctx, *final_args, **final_kwargs)
        except Exception as e:
            raise CommandInvokeError(ctx) from e
