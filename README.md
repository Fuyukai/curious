# Curious

Curious is a Python wrapper for the Discord API, using 
[curio](https://github.com/dabeaz/curio).

Curious **only supports bot accounts**. There will be zero effort made
to support any client-only features, or other features that only user
accounts can use.

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

Curious requires a curio version newer than the one on PyPI currently,
so you must install curio from Git first.

```bash
$ pip install -U git+https://github.com/dabeaz/curio.git#egg=curio
```
