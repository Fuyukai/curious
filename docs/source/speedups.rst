
Optional speedups
=================

curious can make the use of some optional speedups gained by installing C modules instead of pure
python modules.

HTTP handling
-------------

Installing ``lru-dict`` over ``pylru`` can cause some speedups when making HTTP requests.

.. code-block:: bash

    $ pip install -U lru-dict


Gateway handling
----------------

By default, curious uses the built-in ``json`` module to decode messages from the gateway.
Performance can be improved in one of two ways:

 - Switching to use an ETF parser and ETF over the gateway
 - Installing uJSON as the JSON loader/dumper

To switch to ETF:

.. code-block:: bash

    $ pip install -U Earl

To install uJSON:

.. code-block:: bash

    $ pip install -U ujson

curious will automatically detect when these modules are installed and use them.

