"""One value of each kind that typed JSON carries, in the order of the keywords of TypedValuesLib."""

import datetime
import decimal
import pathlib
import uuid
from collections import OrderedDict

from typed_values_types import Color, Level, Pair, Point

TYPED_VALUES = [
    Point(1, 2),
    Pair(1, "a"),
    Color.RED,
    datetime.datetime(2025, 12, 18, 14, 30, tzinfo=datetime.UTC),
    decimal.Decimal("1.50"),
    bytes([0, 1]),
    uuid.UUID("123e4567-e89b-12d3-a456-426614174000"),
    pathlib.Path("folder") / "file.txt",
    (1, "a"),
    {1, 2},
    {1: "a"},
    float("nan"),
    datetime.date(2025, 12, 18),
    datetime.time(14, 30, 15),
    datetime.timedelta(minutes=1, seconds=30.5),
    bytearray([0, 1]),
    frozenset({1, 2}),
    OrderedDict([("b", 2), ("a", 1)]),
    Level.HIGH,
]
