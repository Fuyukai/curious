.. curious documentation master file, created by
   sphinx-quickstart on Fri Dec 30 01:31:23 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to curious's documentation!
===================================

``curious`` is a Python 3.6+ library to interact with the
`Discord <https://discordapp.com>`_ API

Advantages of Curious
---------------------

    - High-level; abstractions are provided at every layer for ease of use
    - Fast; curious can load your bot and begin processing in a matter of seconds
    - Safe; curious validates your data client-side, preventing using up ratelimits on bogus
      requests
    - Powerful; curious exposes every layer of interaction with the Discord API for your usage
    - async; Based on top off the ``curio`` or ``trio`` libraries for a pleasant async experience.


Installation
------------

Curious is available on PyPI under ``discord-curious``:

.. code-block:: bash

    $ pip install -U discord-curious


Or for the latest development version:

.. code-block:: bash

    $ pip install -U git+https://github.com/Fuyukai/curious.git#egg=curious

Examples
--------

Examples for how to use the library are available at
https://github.com/Fuyukai/curious/tree/master/examples.


Documentation
-------------

.. toctree::
    :maxdepth: 2

    tutorial/gettingstarted
    tutorial/firstbot
    tutorial/commands
    tutorial/better_event_handling

    tutorial/objects/channel

    events

    changelog

API Documentation
-----------------

The documentation below is automatically generated from the docstrings.

.. toctree::
    :caption: Autosummary
    :maxdepth: 3

    autogen/curious


Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
