# Curious

Curious is a Python wrapper for the Discord API, using 
[curio](https://github.com/dabeaz/curio).

Curious **only supports bot accounts**. There will be zero effort made 
to support any client-only features, or other features that only user 
accounts can use.

Curious is a WIP - not everything is implemented yet.

## Installation

Curious is not currently available on PyPI, which means you need to 
install it from `git`, instead.

```bash
# install dependencies
$ pip install -U curio curio_websocket multidict
# install the library
$ pip install -U git+https://github.com/SunDwarf/curious.git#egg=curious
```

## Requirements

Curious only runs on Python 3.5 and higher, due to curio only running on
those versions. Additionally, curious currently only works on POSIX
systems due to curio only running on those systems.
