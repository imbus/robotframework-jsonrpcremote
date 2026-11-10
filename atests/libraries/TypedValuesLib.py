"""Test-only library, loaded on the server: keywords whose arguments and return values have declared types.

Each ``Same ...`` keyword checks that the value arrived as its declared type and returns it unchanged.
"""

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from ServerOnlyTypes import OnlyOnTheServer
from typed_values_types import Color, Level, Pair, Point

_T = TypeVar("_T")


def _checked(value: _T, cls: type) -> _T:
    if not isinstance(value, cls):
        raise AssertionError(f"Got {value!r} of type {type(value).__name__}, not {cls.__name__}.")
    return value


class TypedValuesLib:
    def same_point(self, value: Point) -> Point:
        return _checked(value, Point)

    def same_pair(self, value: Pair) -> Pair:
        return _checked(value, Pair)

    def same_color(self, value: Color) -> Color:
        return _checked(value, Color)

    def same_datetime(self, value: datetime) -> datetime:
        return _checked(value, datetime)

    def same_decimal(self, value: Decimal) -> Decimal:
        return _checked(value, Decimal)

    def same_bytes(self, value: bytes) -> bytes:
        return _checked(value, bytes)

    def same_uuid(self, value: UUID) -> UUID:
        return _checked(value, UUID)

    def same_path(self, value: Path) -> Path:
        return _checked(value, Path)

    def same_tuple(self, value: tuple[int, str]) -> tuple[int, str]:
        return _checked(value, tuple)

    def same_set(self, value: set[int]) -> set[int]:
        return _checked(value, set)

    def same_int_keys(self, value: dict[int, str]) -> dict[int, str]:
        return _checked(value, dict)

    def same_float(self, value: float) -> float:
        return _checked(value, float)

    def same_date(self, value: date) -> date:
        return _checked(value, date)

    def same_time(self, value: time) -> time:
        return _checked(value, time)

    def same_timedelta(self, value: timedelta) -> timedelta:
        return _checked(value, timedelta)

    def same_bytearray(self, value: bytearray) -> bytearray:
        return _checked(value, bytearray)

    def same_frozenset(self, value: frozenset[int]) -> frozenset[int]:
        return _checked(value, frozenset)

    def same_ordered_dict(self, value: OrderedDict[str, int]) -> OrderedDict[str, int]:
        return _checked(value, OrderedDict)

    def same_level(self, value: Level) -> Level:
        return _checked(value, Level)

    def describe_named(self, *, point: Point, color: Color) -> str:
        """Takes its arguments only by name, and returns the names of their types and the color."""
        return f"{type(_checked(point, Point)).__name__} {_checked(color, Color).name}"

    def sum_points(self, *points: Point) -> Point:
        """Returns the sum of the points that it got as variable arguments."""
        return Point(sum(_checked(point, Point).x for point in points), sum(point.y for point in points))

    def colors_by_name(self, **colors: Color) -> dict[str, Color]:
        """Returns the colors that it got as free named arguments."""
        return {name: _checked(color, Color) for name, color in colors.items()}

    def points_by_name(self, **points: Point) -> dict[str, Point]:
        """Returns the points that it got as free named arguments."""
        return {name: _checked(point, Point) for name, point in points.items()}

    def same_any(self, value: Any) -> Any:
        """Returns the value that it got, without a declared type."""
        return value

    def type_name_of(self, value: Any) -> str:
        """Returns the module and the qualified name of the type of the value that it got."""
        return f"{type(value).__module__}.{type(value).__qualname__}"

    def make_declared_only_on_the_server(self) -> OnlyOnTheServer:
        """Returns an instance of a class that the client does not have, with the class as its declared type."""
        return OnlyOnTheServer(1)

    def make_only_on_the_server(self) -> Any:
        """Returns an instance of a class that the client does not have, without a declared type."""
        return OnlyOnTheServer(1)
