"""
Voice connection utilities.

.. currentmodule:: curious.voice

.. autosummary::
    :toctree: voice

    voice_client
    voice_gateway
    voice_player
"""
try:
    import opuslib
except ImportError as e:
    raise ImportError("You must install `opuslib` to use curious' voice") from e

try:
    import nacl
except ImportError as e:
    raise ImportError("You must install `pynacl` to use curious' voice") from e

from .voice_player import VoicePlayer
from .voice_client import VoiceClient
