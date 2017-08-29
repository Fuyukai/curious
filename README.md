# Curious

Curious is a Python 3.6+ wrapper for the Discord API, using
[curio](https://github.com/dabeaz/curio).

## Installation

Curious is available on PyPI under `discord-curious`:

```bash
$ pip install -U discord-curious
```

Or for the latest development version:

```bash
$ pip install -U git+https://github.com/SunDwarf/curious.git#egg=curious
```

## Basic Example

```py
from curious import BotType, Client, Message

cl = Client("token", bot_type=BotType.BOT | BotType.NO_DMS, command_prefix="!")


@cl.event("ready")
async def ready(ctx):
    print("Ready on shard", ctx.shard_id)


@cl.event("message_create")
async def handle_message(ctx, message: Message):
    print(f"{message.author.user.name} said '{message.content}'")

cl.run(shards=1)
```

## Documentation

See the documentation at https://curious.readthedocs.io/en/latest/.

