"""The value format of the protocol: plain JSON, pickles by the agreement, and typed values."""

import collections
import datetime
import decimal
import math
import os
import pathlib
import pickle
import re
import types
import uuid
from collections import OrderedDict
from typing import Any, Optional

import pytest
from value_types import Color, Event, Level, Outer, Pair, Point, Text, Widget

from robot_jsonrpcremote_protocol import (
    PICKLED_KEY,
    TYPE_KEY,
    PickleNotAgreedError,
    ValueCannotTravelError,
    ValueDoesNotFitError,
    ValueFormat,
    agreed_pickle_protocol,
    type_name,
    unresolved_type,
)

WITH_PICKLES = ValueFormat(pickle_protocol=5)
WITHOUT_PICKLES = ValueFormat()
FORMATS = pytest.mark.parametrize("value_format", [WITH_PICKLES, WITHOUT_PICKLES], ids=["pickles", "no pickles"])


class FakeDotDict(dict[str, Any]):
    """Stands for Robot Framework's DotDict, which the protocol package does not know."""


def _protocol_of(data: dict[str, str]) -> int:
    raw = bytes.fromhex(data[PICKLED_KEY])
    assert raw[0] == pickle.PROTO[0]
    return raw[1]


def _same(left: Any, right: Any) -> bool:
    """Equal and of the same type; NaN counts as equal to NaN."""
    if isinstance(left, float) and math.isnan(left):
        return isinstance(right, float) and math.isnan(right)
    return type(left) is type(right) and left == right


# --- the agreement -------------------------------------------------------------------------------------------------


def test_pickles_are_agreed_with_the_lower_protocol() -> None:
    assert agreed_pickle_protocol(5, 4) == 4
    assert agreed_pickle_protocol(4, 5) == 4


@pytest.mark.parametrize(("ours", "theirs"), [(5, None), (None, 5), (None, None)])
def test_no_pickles_are_agreed_when_one_side_states_none(ours: int | None, theirs: int | None) -> None:
    assert agreed_pickle_protocol(ours, theirs) is None


# --- plain JSON ---------------------------------------------------------------------------------------------------


@FORMATS
def test_json_values_travel_as_plain_json(value_format: ValueFormat) -> None:
    value = [1, 2.5, {"a": [True, None, "x"]}]

    encoded = value_format.encode(value)

    assert encoded == value
    assert value_format.decode(encoded) == value


@FORMATS
def test_a_further_dict_type_comes_back_as_a_plain_dict(value_format: ValueFormat) -> None:
    with_dot_dict = ValueFormat(value_format.pickle_protocol, dict_types=(FakeDotDict,))

    encoded = with_dot_dict.encode(FakeDotDict(a=1))

    assert type(encoded) is dict
    assert encoded == {"a": 1}
    assert type(with_dot_dict.decode(encoded)) is dict


def test_null_is_none_for_a_declared_type() -> None:
    assert WITHOUT_PICKLES.decode(None, datetime.datetime) is None


# --- pickles --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("protocol", [4, 5])
def test_a_value_without_a_declared_type_is_pickled_with_the_agreed_protocol(protocol: int) -> None:
    value_format = ValueFormat(pickle_protocol=protocol)

    encoded = value_format.encode((1, 2))

    assert set(encoded) == {PICKLED_KEY}
    assert _protocol_of(encoded) == protocol
    assert value_format.decode(encoded) == (1, 2)


def test_a_list_that_holds_a_tuple_is_one_pickle() -> None:
    encoded = WITH_PICKLES.encode([1, (2, 3)])

    assert set(encoded) == {PICKLED_KEY}
    assert WITH_PICKLES.decode(encoded) == [1, (2, 3)]


@pytest.mark.parametrize("value", [Level.HIGH, OrderedDict(a=1), Text("x")], ids=["IntEnum", "OrderedDict", "str"])
def test_subclasses_of_the_json_types_are_pickled_and_keep_their_type(value: Any) -> None:
    encoded = WITH_PICKLES.encode(value)

    assert set(encoded) == {PICKLED_KEY}
    assert _same(WITH_PICKLES.decode(encoded), value)


def test_nan_without_a_declared_type_is_a_pickle() -> None:
    encoded = WITH_PICKLES.encode(float("nan"))

    assert set(encoded) == {PICKLED_KEY}
    assert math.isnan(WITH_PICKLES.decode(encoded))


def test_a_value_that_cannot_be_pickled_names_it() -> None:
    with pytest.raises((AttributeError, pickle.PicklingError), match="lambda"):
        WITH_PICKLES.encode(lambda: None)


@pytest.mark.parametrize("key", [PICKLED_KEY, TYPE_KEY])
def test_a_dict_with_a_marker_key_is_pickled(key: str) -> None:
    encoded = WITH_PICKLES.encode({key: "x"})

    assert set(encoded) == {PICKLED_KEY}
    assert WITH_PICKLES.decode(encoded) == {key: "x"}


@pytest.mark.parametrize("key", [PICKLED_KEY, TYPE_KEY])
def test_a_dict_with_a_marker_key_cannot_travel_without_pickles(key: str) -> None:
    with pytest.raises(ValueCannotTravelError):
        WITHOUT_PICKLES.encode({key: "x"})


def test_an_object_of_an_unsupported_class_cannot_travel_without_pickles() -> None:
    with pytest.raises(TypeError, match=r"value_types\.Widget"):
        WITHOUT_PICKLES.encode(Widget("w"))


@pytest.mark.parametrize(
    ("value", "name"),
    [(Text("x"), "value_types.Text"), (collections.defaultdict(int), "collections.defaultdict")],
    ids=["str", "defaultdict"],
)
def test_other_subclasses_of_the_json_types_cannot_travel_without_pickles(value: Any, name: str) -> None:
    with pytest.raises(TypeError, match=re.escape(name)):
        WITHOUT_PICKLES.encode(value)


def test_a_pickle_without_the_agreement_is_not_unpickled() -> None:
    # Unpickling it would import a module that does not exist.
    data = {PICKLED_KEY: b"cmodule_that_does_not_exist\nThing\n.".hex()}

    with pytest.raises(PickleNotAgreedError):
        WITHOUT_PICKLES.decode(data)
    with pytest.raises(ModuleNotFoundError):
        WITH_PICKLES.decode(data)


# --- typed values of a declared type --------------------------------------------------------------------------------


@FORMATS
def test_a_declared_dataclass_travels_as_its_fields(value_format: ValueFormat) -> None:
    encoded = value_format.encode(Point(1, 2), Point)

    assert encoded == {"x": 1, "y": 2}
    assert _same(value_format.decode(encoded, Point), Point(1, 2))


@FORMATS
def test_a_declared_named_tuple_and_enum_travel_in_their_forms(value_format: ValueFormat) -> None:
    assert value_format.encode(Pair(1, "a"), Pair) == [1, "a"]
    assert value_format.encode(Color.RED, Color) == "RED"
    assert _same(value_format.decode([1, "a"], Pair), Pair(1, "a"))
    assert value_format.decode("RED", Color) is Color.RED


BUILT_IN_VALUES = [
    ((1, 2), tuple[int, int], [1, 2]),
    ((1, 2, 3), tuple[int, ...], [1, 2, 3]),
    ({1, 2}, set[int], [1, 2]),
    (frozenset({1}), frozenset[int], [1]),
    ({1: "a"}, dict[int, str], [[1, "a"]]),
    (OrderedDict(a=1), OrderedDict[str, int], {"a": 1}),
    (float("nan"), float, "NaN"),
    (float("inf"), float, "Infinity"),
    (float("-inf"), float, "-Infinity"),
]


@FORMATS
@pytest.mark.parametrize(("value", "declared", "form"), BUILT_IN_VALUES, ids=lambda case: repr(case)[:20])
def test_declared_built_in_values_travel_in_their_forms(
    value_format: ValueFormat, value: Any, declared: Any, form: Any
) -> None:
    encoded = value_format.encode(value, declared)

    assert sorted(encoded) == sorted(form) if isinstance(value, (set, frozenset)) else encoded == form
    assert _same(value_format.decode(encoded, declared), value)


_UTC_TIME = datetime.datetime(2025, 12, 18, 14, 30, tzinfo=datetime.UTC)
# A path in the notation of the platform, written with / on the wire.
_PATH, _PATH_FORM = (pathlib.Path("C:\\tmp\\x"), "C:/tmp/x") if os.name == "nt" else (pathlib.Path("/tmp/x"), "/tmp/x")
_UUID = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")

STANDARD_VALUES = [
    (_UTC_TIME, datetime.datetime, "2025-12-18T14:30:00+00:00"),
    (_UTC_TIME.replace(tzinfo=None), datetime.datetime, "2025-12-18T14:30:00"),
    (datetime.date(2025, 12, 18), datetime.date, "2025-12-18"),
    (datetime.time(14, 30), datetime.time, "14:30:00"),
    (datetime.timedelta(minutes=1, seconds=30.5), datetime.timedelta, 90.5),
    (decimal.Decimal("123.45"), decimal.Decimal, "123.45"),
    (_UUID, uuid.UUID, "123e4567-e89b-12d3-a456-426614174000"),
    (b"\x00\x01", bytes, "AAE="),
    (bytearray(b"\x00\x01"), bytearray, "AAE="),
    (_PATH, pathlib.Path, _PATH_FORM),
]


@FORMATS
@pytest.mark.parametrize(("value", "declared", "form"), STANDARD_VALUES, ids=lambda case: repr(case)[:24])
def test_declared_standard_types_travel_in_their_forms(
    value_format: ValueFormat, value: Any, declared: Any, form: Any
) -> None:
    encoded = value_format.encode(value, declared)

    assert encoded == form
    assert _same(value_format.decode(encoded, declared), value)


@FORMATS
def test_declared_values_inside_lists_and_dicts(value_format: ValueFormat) -> None:
    assert value_format.encode([Point(1, 2)], list[Point]) == [{"x": 1, "y": 2}]
    assert value_format.decode([{"x": 1, "y": 2}], list[Point]) == [Point(1, 2)]
    assert value_format.encode({"a": Color.RED}, dict[str, Color]) == {"a": "RED"}
    assert value_format.decode({"a": "RED"}, dict[str, Color]) == {"a": Color.RED}


@FORMATS
def test_the_fields_of_a_dataclass_travel_in_their_forms(value_format: ValueFormat) -> None:
    event = Event("start", _UTC_TIME, Point(1, 2), ("a", "b"))

    encoded = value_format.encode(event, Event)

    assert encoded == {
        "name": "start",
        "at": "2025-12-18T14:30:00+00:00",
        "where": {"x": 1, "y": 2},
        "tags": ["a", "b"],
        "seen": 0,
    }
    assert value_format.decode(encoded, Event) == event


def test_a_declared_enum_travels_as_its_name_with_pickles() -> None:
    assert WITH_PICKLES.encode(Color.RED, Color) == "RED"


def test_a_value_that_is_not_of_its_declared_type_travels_as_without_one() -> None:
    assert WITHOUT_PICKLES.encode("abc", datetime.datetime) == "abc"
    assert set(WITH_PICKLES.encode(Widget("w"), Point)) == {PICKLED_KEY}
    with pytest.raises(ValueCannotTravelError):
        WITHOUT_PICKLES.encode(Widget("w"), Point)


@FORMATS
def test_decoding_a_form_that_does_not_fit_its_declared_type_fails(value_format: ValueFormat) -> None:
    with pytest.raises(ValueDoesNotFitError, match="datetime") as error:
        value_format.decode("abc", datetime.datetime)
    assert error.value.type_name == "datetime"


# --- typed values without a declared type ---------------------------------------------------------------------------


def test_an_undeclared_dataclass_names_its_type() -> None:
    encoded = WITHOUT_PICKLES.encode(Point(1, 2))

    assert encoded == {TYPE_KEY: "value_types.Point", "x": 1, "y": 2}
    assert _same(WITHOUT_PICKLES.decode(encoded), Point(1, 2))


def test_undeclared_built_in_and_standard_values_name_their_type() -> None:
    assert WITHOUT_PICKLES.encode((1, 2), Any) == {TYPE_KEY: "tuple", "value": [1, 2]}
    assert WITHOUT_PICKLES.encode(_UTC_TIME, int | datetime.datetime) == {
        TYPE_KEY: "datetime",
        "value": "2025-12-18T14:30:00+00:00",
    }
    assert _same(WITHOUT_PICKLES.decode({TYPE_KEY: "tuple", "value": [1, 2]}), (1, 2))
    assert _same(WITHOUT_PICKLES.decode({TYPE_KEY: "datetime", "value": "2025-12-18T14:30:00+00:00"}), _UTC_TIME)


@pytest.mark.parametrize("declared", [Point | None, Optional[Point]], ids=["|", "Optional"])
def test_a_union_with_none_declares_the_type(declared: Any) -> None:
    assert WITHOUT_PICKLES.encode(Point(1, 2), declared) == {"x": 1, "y": 2}


def test_undeclared_typed_values_inside_a_list() -> None:
    encoded = WITHOUT_PICKLES.encode([Point(1, 2), (3, 4)])

    assert encoded == [{TYPE_KEY: "value_types.Point", "x": 1, "y": 2}, {TYPE_KEY: "tuple", "value": [3, 4]}]
    assert WITHOUT_PICKLES.decode(encoded) == [Point(1, 2), (3, 4)]


def test_a_nested_class_is_named_with_its_qualified_name() -> None:
    encoded = WITHOUT_PICKLES.encode(Outer.Inner(1))

    assert encoded[TYPE_KEY] == "value_types.Outer.Inner"
    assert WITHOUT_PICKLES.decode(encoded) == Outer.Inner(1)


def test_a_standard_type_is_named_as_by_robot_framework() -> None:
    assert WITHOUT_PICKLES.encode(decimal.Decimal("1"))[TYPE_KEY] == "Decimal"
    assert type_name(type(pathlib.Path("x"))) == "Path"


def test_decoding_a_name_of_something_else_fails() -> None:
    with pytest.raises(ValueDoesNotFitError, match=r"os\.path\.join"):
        WITHOUT_PICKLES.decode({TYPE_KEY: "os.path.join", "value": ["a", "b"]})


def test_decoding_a_class_that_is_not_supported_fails() -> None:
    with pytest.raises(ValueDoesNotFitError, match="defaultdict"):
        WITHOUT_PICKLES.decode({TYPE_KEY: "collections.defaultdict", "value": {}})


def test_decoding_a_dataclass_with_a_missing_field_fails() -> None:
    with pytest.raises(ValueDoesNotFitError, match=r"value_types\.Point: missing field 'y'"):
        WITHOUT_PICKLES.decode({"x": 1}, Point)


def test_decoding_a_class_that_is_not_installed_fails() -> None:
    with pytest.raises(ValueDoesNotFitError, match=r"notinstalled\.Point.*No module named 'notinstalled'"):
        WITHOUT_PICKLES.decode({TYPE_KEY: "notinstalled.Point", "x": 1})


# --- classes that cannot be imported --------------------------------------------------------------------------------

_MISSING = unresolved_type("notinstalled.Point", "No module named 'notinstalled'")


@FORMATS
def test_decoding_a_value_for_an_unresolved_type_fails(value_format: ValueFormat) -> None:
    with pytest.raises(
        ValueDoesNotFitError, match=r"notinstalled\.Point: it cannot be imported: No module named 'notinstalled'$"
    ):
        value_format.decode({"x": 1, "y": 2}, _MISSING)


@FORMATS
def test_null_and_an_empty_list_need_nothing_of_an_unresolved_type(value_format: ValueFormat) -> None:
    assert value_format.decode(None, _MISSING) is None
    assert value_format.decode(None, _MISSING | None) is None
    assert value_format.decode([], types.GenericAlias(list, (_MISSING,))) == []


def test_a_value_at_the_place_of_an_unresolved_type_travels_as_without_one() -> None:
    assert WITHOUT_PICKLES.encode({"x": 1, "y": 2}, _MISSING) == {"x": 1, "y": 2}
    assert set(WITH_PICKLES.encode(Point(1, 2), _MISSING)) == {PICKLED_KEY}
