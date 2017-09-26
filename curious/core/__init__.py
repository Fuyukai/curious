"""
The core of Curious.

This package contains the bulk of the network interface with Discord, including parsing data that is incoming and 
delegating it to client code.

.. currentmodule:: curious.core

.. autosummary::
    :toctree: core
    
    client
    event
    gateway
    httpclient
    state
"""
import asks
import multio

if asks.init != multio.init:
    _init = multio.init
    multio.init = lambda lib: (asks.init(lib), _init(lib))

multio.init("curio")
