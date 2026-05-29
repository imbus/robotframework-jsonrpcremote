from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

import pytest

from jsonrpcpeer.json_helpers import (
    CamelSnakeMixin,
    TypeValidationError,
    ValidateMixin,
    as_dict,
    as_json,
    from_dict,
    from_json,
    jsonable_to_value,
    to_camel_case,
    to_snake_case,
    value_to_jsonable,
)


class Color(str, Enum):
    RED = "RED"
    GREEN = "GREEN"


@dataclass
class Point:
    x: int
    y: int


@dataclass
class CamelInfo(CamelSnakeMixin):
    client_name: str
    retry_count: int = 0


@dataclass
class HasColor:
    c: Color


@dataclass
class A1:
    x: int


@dataclass
class B1:
    x: int


@dataclass
class Validated(ValidateMixin):
    n: int


# --- case conversion -------------------------------------------------------


def test_to_snake_case() -> None:
    assert to_snake_case("clientInfo") == "client_info"
    assert to_snake_case("name") == "name"


def test_to_camel_case() -> None:
    assert to_camel_case("client_info") == "clientInfo"
    assert to_camel_case("client-info") == "clientInfo"


def test_casing_roundtrip() -> None:
    assert to_camel_case(to_snake_case("clientInfo")) == "clientInfo"


# --- from_dict: scalars / unions / literals / enums ------------------------


def test_from_dict_basic_types() -> None:
    assert from_dict(5, int) == 5
    assert from_dict("x", str) == "x"
    assert from_dict(True, bool) is True


def test_from_dict_int_to_float_coercion() -> None:
    result = from_dict(5, float)
    assert result == 5.0
    assert isinstance(result, float)


def test_from_dict_strict_disables_coercion() -> None:
    with pytest.raises(TypeError):
        from_dict(5, float, strict=True)


def test_from_dict_optional() -> None:
    assert from_dict(None, Optional[int]) is None
    assert from_dict(7, Optional[int]) == 7


def test_from_dict_union() -> None:
    assert from_dict("x", (int, str)) == "x"


def test_from_dict_literal() -> None:
    assert from_dict("a", Literal["a", "b"]) == "a"
    with pytest.raises(TypeError):
        from_dict("c", Literal["a", "b"])


def test_from_dict_enum() -> None:
    assert from_dict("RED", Color) is Color.RED
    with pytest.raises(TypeError):
        from_dict("PURPLE", Color)


# --- from_dict: containers / dataclasses -----------------------------------


def test_from_dict_sequence_preserves_order_and_duplicates() -> None:
    assert from_dict([3, 1, 1, 2], list[int]) == [3, 1, 1, 2]


def test_from_dict_mapping() -> None:
    assert from_dict({"a": 1, "b": 2}, dict[str, int]) == {"a": 1, "b": 2}


def test_from_dict_dataclass_plain() -> None:
    assert from_dict({"x": 1, "y": 2}, Point) == Point(1, 2)


def test_from_dict_dataclass_camel_decoding() -> None:
    assert from_dict({"clientName": "bob", "retryCount": 3}, CamelInfo) == CamelInfo("bob", 3)


def test_from_dict_ambiguous_union_raises() -> None:
    with pytest.raises(TypeError):
        from_dict({"x": 1}, (A1, B1))


# --- as_dict / as_json -----------------------------------------------------


def test_as_dict_plain() -> None:
    assert as_dict(Point(1, 2)) == {"x": 1, "y": 2}


def test_as_dict_camel_encoding() -> None:
    assert as_dict(CamelInfo("bob", 3)) == {"clientName": "bob", "retryCount": 3}


def test_as_dict_enum_value() -> None:
    assert as_dict(HasColor(Color.RED)) == {"c": "RED"}


def test_as_json_roundtrip() -> None:
    p = Point(3, 4)
    assert from_json(as_json(p), Point) == p


# --- pickle-backed object transfer -----------------------------------------


def test_value_to_jsonable_primitives() -> None:
    for v in (5, "x", 3.14, True):
        assert value_to_jsonable(v) == v
    assert value_to_jsonable(None) is None


def test_object_pickle_roundtrip() -> None:
    obj = complex(1, 2)
    encoded = value_to_jsonable(obj)
    assert isinstance(encoded, dict)
    assert "__pickled__" in encoded
    assert jsonable_to_value(encoded) == obj


def test_jsonable_to_value_passthrough() -> None:
    assert jsonable_to_value({"a": 1}) == {"a": 1}
    assert jsonable_to_value(None) is None


# --- ValidateMixin ---------------------------------------------------------


def test_validate_mixin_accepts_valid() -> None:
    assert Validated(5).n == 5


def test_validate_mixin_rejects_invalid() -> None:
    with pytest.raises(TypeValidationError):
        Validated("not an int")  # type: ignore[arg-type]
