"""Types of TypedValuesLib, which client and server import by this module's name, as the protocol asks."""

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


@dataclass
class Point:
    x: int
    y: int


class Pair(NamedTuple):
    first: int
    second: str


class Color(Enum):
    RED = "red"
    GREEN = "green"
