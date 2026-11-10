"""The types that client and server share: both import this module by its name, shapes."""

from dataclasses import dataclass
from enum import Enum


@dataclass
class Point:
    x: int
    y: int


class Color(Enum):
    RED = "red"
    GREEN = "green"
