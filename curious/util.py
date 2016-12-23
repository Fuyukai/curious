"""
Misc utilities shared throughout the library.
"""
import datetime


def to_datetime(timestamp: str) -> datetime.datetime:
    """
    Converts a Discord-formatted timestamp to a datetime object.

    :param timestamp: The timestamp to convert.
    :return: The :class:`datetime.datetime` object that corresponds to this datetime.
    """
    return datetime.datetime.strptime(timestamp[:-6], "%Y-%m-%dT%H:%M:%S.%f")
