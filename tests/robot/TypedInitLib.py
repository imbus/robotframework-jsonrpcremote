"""Test library with a typed __init__, to check server-side conversion of arguments.

Loaded on the server via --pythonpath. The client only ever sends strings/JSON; Robot
converts them to the declared types on the server:
  * enums and built-in types are converted for init arguments out of the box,
  * custom-type converters (registered via @library) apply to keyword *calls* but NOT
    to library *init* arguments -- a documented Robot behaviour.
"""

from enum import Enum

from robot.api.deco import library


class Mode(Enum):
    SLOW = "slow"
    FAST = "fast"


class Tag:
    """A custom type, converted from a string via the registered converter below."""

    def __init__(self, value: str) -> None:
        self.value = value


@library(scope="TEST", converters={Tag: Tag}, auto_keywords=True)
class TypedInitLib:
    def __init__(self, mode: Mode = Mode.SLOW, count: int = 0, tag: "Tag | None" = None) -> None:
        self._mode = mode
        self._count = count
        self._tag = tag

    def get_mode_name(self) -> str:
        return self._mode.name

    def get_mode_type(self) -> str:
        return type(self._mode).__name__

    def get_init_count(self) -> int:
        return self._count

    def get_init_count_type(self) -> str:
        return type(self._count).__name__

    def get_tag_type(self) -> str:
        return type(self._tag).__name__

    def tag_type_of(self, value: Tag) -> str:
        """Keyword whose argument is the custom type, where the converter does apply."""
        return type(value).__name__
