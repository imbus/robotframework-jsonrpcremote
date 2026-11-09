"""One value of each kind that typed JSON carries, in the order of the keywords of TypedValuesLib."""

import datetime
import decimal
import pathlib
import uuid

from typed_values_types import Color, Pair, Point

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
]
