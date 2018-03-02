# This file is part of curious.
#
# curious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# curious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with curious.  If not, see <http://www.gnu.org/licenses/>.

"""
Base classes that all dataclasses inherit from.

.. currentmodule:: curious.dataclasses.bases
"""
import datetime
import inspect
import sys
import threading
from contextlib import contextmanager

from curious.core import client

DISCORD_EPOCH = 1420070400000

_allowing_external_makes = threading.local()
_allowing_external_makes.flag = False


@contextmanager
def allow_external_makes() -> None:
    """
    Using this with a ``with`` allows dataclasses to be made outside of curious' internal code.
    """
    try:
        _allowing_external_makes.flag = True
        yield
    finally:
        _allowing_external_makes.flag = False


class IDObject(object):
    """
    This object is comparable using the snowflake as an ID.

    It is also hashable, using the ID as a hash.
    """

    __slots__ = "id",

    def __init__(self, id: int):
        """
        :param id: The snowflake ID of the object.
        """
        if isinstance(id, str):
            id = int(id)

        #: The ID of this object.
        self.id = id

    def __repr__(self) -> str:
        return "<{} id={!r}>".format(self.__class__.__name__, self.id)

    __str__ = __repr__

    @property
    def snowflake_timestamp(self) -> datetime.datetime:
        """
        :return: The timestamp of the snowflake.
        """
        return datetime.datetime.utcfromtimestamp(((int(self.id) >> 22) + DISCORD_EPOCH) / 1000)

    def __eq__(self, other) -> bool:
        if not hasattr(other, "id"):
            return NotImplemented

        return other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)


class Dataclass(IDObject):
    """
    The base class for all dataclasses.

    These contain a reference to the current bot as `_bot`.
    """

    # __weakref__ is used to allow weakreffing
    __slots__ = "_bot", "__weakref__"

    @staticmethod
    def __new__(cls, *args, **kwargs):
        """
        Inspects the stack to ensure we're being called correctly.
        """
        if _allowing_external_makes.flag is False:
            try:
                frameinfo = inspect.stack()[1]
                frame = frameinfo.frame
                f_globals = frame.f_globals
                f_name = frame.f_code.co_name
                module = f_globals.get('__name__', None)
                file = f_globals.get('__file__', None)

                if module is not None:
                    if f_name == "_convert" and module.startswith("curious.commands"):
                        raise RuntimeError("You passed a dataclass ({}) as a type hint to your "
                                           "command without a converter - don't do this!\n"
                                           "This error has been raised because no builtin converter"
                                           " exists, or the built-in converter has been replaced. "
                                           "Make sure to either add one or fix your code to use a "
                                           "converter function!".format(cls.__name__))
                    elif not module.startswith("curious") \
                            and f'/python3.{sys.version_info[1]}' not in file:
                        raise RuntimeError("You tried to make a dataclass manually - don't do this!"
                                           "\nThe library handles making dataclasses for you. If "
                                           "you want to get an instance, use the appropriate "
                                           "lookup method. \nIf you really need to make the "
                                           "dataclass yourself, wrap it in a "
                                           "``with allow_external_makes)``.")
            finally:
                del frameinfo, frame

        return object.__new__(cls)

    def __init__(self, id: int, cl: 'client.Client'):
        super().__init__(id)

        self._bot = cl
