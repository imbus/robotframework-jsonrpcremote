"""Test library with a richly typed __init__, to exercise server-side argument conversion.

Loaded on the server via --pythonpath. The client only ever sends strings/JSON; Robot
converts them to the declared types on the server using this __init__ signature. This
covers the common conversions (enum, numbers, bool, Decimal, date, list/dict/set with
nested item types). Custom-type converters (registered via @library) apply to keyword
*calls* but NOT to library *init* arguments -- a documented Robot behaviour.
"""

from datetime import date
from decimal import Decimal
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
    def __init__(
        self,
        mode: Mode,
        count: int,
        ratio: float,
        flag: bool,
        amount: Decimal,
        when: date,
        items: list[int],
        mapping: dict[str, int],
        tags: set[str],
        tag: "Tag | None" = None,
    ) -> None:
        self._mode = mode
        self._values: dict[str, object] = {
            "mode": mode,
            "count": count,
            "ratio": ratio,
            "flag": flag,
            "amount": amount,
            "when": when,
            "items": items,
            "mapping": mapping,
            "tags": tags,
            "tag": tag,
        }

    def get_arg_types(self) -> dict[str, str]:
        """Returns a map of init-argument name to the type name it was converted to."""
        return {name: type(value).__name__ for name, value in self._values.items()}

    def get_value(self, name: str) -> object:
        """Returns the converted init-argument value for the given name."""
        return self._values[name]

    def get_mode_name(self) -> str:
        return self._mode.name

    def tag_type_of(self, value: Tag) -> str:
        """Keyword whose argument is the custom type, where the converter does apply."""
        return type(value).__name__
