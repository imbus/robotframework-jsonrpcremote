"""Types for the tests of the value format, in a module of their own, so that their names are ``value_types.*``."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import NamedTuple


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Event:
    """A dataclass whose fields have types with forms of their own."""

    name: str
    at: datetime
    where: Point
    tags: tuple[str, ...] = ()
    seen: int = field(default=0, init=False)


class Pair(NamedTuple):
    first: int
    second: str


class Color(Enum):
    RED = "red"
    GREEN = "green"


class Level(IntEnum):
    LOW = 1
    HIGH = 2


class Outer:
    @dataclass
    class Inner:
        value: int


class Text(str):
    """A subclass of a JSON type that is no enum."""


class Widget:
    """An object of a class that has no form: no dataclass, enum or named tuple."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Widget) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)
