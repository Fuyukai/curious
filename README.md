# Curious

Curious is a Python wrapper for the Discord API, using 
[curio](https://github.com/dabeaz/curio).

Curious **only supports bot accounts**. There will be zero effort made
to support any client-only features, or other features that only user
accounts can use.

Curious is a WIP - not everything is implemented yet.

## Installation

Curious is available on PyPI under `discord-curious`:

```bash
$ pip install -U discord-curious
```

Or for the latest development version:

```bash
$ pip install -U git+https://github.com/SunDwarf/curious.git#egg=curious
```

## Requirements

Curious only runs on Python 3.5 and higher, due to curio only running on
those versions.
