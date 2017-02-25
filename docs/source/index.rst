.. curious documentation master file, created by
   sphinx-quickstart on Fri Dec 30 01:31:23 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to curious's documentation!
===================================

``curious`` is a Python 3.6+ library to interact with the `Discord <https://discordapp.com>`_ API. It is based on top
of `curio <https://github.com/dabeaz/curio>`_.

Curious **only supports bot accounts**. There will be zero effort made to support any client-only features, or other
features that only user accounts can use.

Installation
------------

Curious is available on PyPI under ``discord-curious``:

.. code-block:: bash

   $ pip install -U discord-curious


Or for the latest development version:

.. code-block:: bash

   $ pip install -U git+https://github.com/SunDwarf/curious.git#egg=curious


Additionally, curious requires the usage of an as-of-yet unreleased version of ``curio``:

.. code-block:: bash

   $ pip install -U git+https://github.com/dabeaz/curio.git

Examples
--------

Examples for how to use the library are available at https://github.com/SunDwarf/curious/tree/master/examples.


.. toctree::
   :maxdepth: 4
   :caption: Contents:

   curious


Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
