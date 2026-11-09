"""The types of the keyword ``Move``: the client imports them by this module's name, as the server does."""

from dataclasses import dataclass


@dataclass
class Point:
    x: int
    y: int
