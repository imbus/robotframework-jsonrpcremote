import collections
import json
import subprocess
import sys
import textwrap
import typing
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, MutableSequence, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Union

import pytest

from jsonrpcpeer.json_helpers import (
    CamelSnakeMixin,
    NamedTypeError,
    TypeValidationError,
    ValidateMixin,
    as_dict,
    as_json,
    from_dict,
    from_json,
    to_camel_case,
    to_snake_case,
    validate_types,
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


class Pair(NamedTuple):
    x: int
    y: str


class One(NamedTuple):
    x: int


class Defaults(NamedTuple):
    x: int = 0
    y: int = 0


Untyped = collections.namedtuple("Untyped", "x y")


class Tags(tuple[Any, ...]):
    pass


@dataclass
class UA:
    a: int


@dataclass
class UB:
    b: int


@dataclass
class TypingUnionItem:
    x: int


@dataclass
class HoldsTypingUnion:
    item: Optional[TypingUnionItem] = None


@dataclass
class KindA:
    kind: Literal["a"]
    value: int


@dataclass
class KindB:
    kind: Literal["b"]
    value: int


@dataclass
class IntX:
    x: int


@dataclass
class StrX:
    x: str


@dataclass
class ItemAB:
    a: int
    b: int


@dataclass
class ItemA:
    a: int


@dataclass
class HoldsAny:
    value: Any = None


@dataclass
class HoldsPoint:
    point: Point


class AnnotatedClass:
    a: int

    def __init__(self, a: int) -> None:
        self.a = a


class PlainClass:
    pass


class AnnotatedText(str):
    a: int


class RejectsItsFields:
    a: int

    def __init__(self, a: int) -> None:
        raise TypeError("rejected")


@dataclass
class FieldsWithMetadata:
    plain: int = 1
    not_saved: str = field(default="s", metadata={"nosave": True})
    no_init: str = field(default="h", init=False)
    no_init_forced: str = field(default="f", init=False, metadata={"force_json": True})
    maybe: Optional[int] = None


@dataclass
class WithFactory:
    tags: List[str] = field(default_factory=list)


class Converters:
    def to_int(self, value: Any) -> int:
        return int(value)


@dataclass
class ConvertedByFunction(ValidateMixin):
    n: int = field(metadata={"convert": lambda _self, value: int(value)})


@dataclass
class ConvertedByMethod(ValidateMixin):
    n: int = field(metadata={"convert": Converters().to_int})


@dataclass
class CheckedByFunction(ValidateMixin):
    n: int = field(metadata={"validate": lambda _self, value: ["negative"] if value < 0 else []})


# --- case conversion -------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("clientInfo", "client_info"),
        ("name", "name"),
        ("a.b", "a_b"),
        ("a b", "a_b"),
        ("a-b", "a_b"),
        ("", ""),
        ("_name", "_name"),
        ("HTTPServer", "h_t_t_p_server"),
    ],
)
def test_to_snake_case(name: str, expected: str) -> None:
    assert to_snake_case(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("client_info", "clientInfo"),
        ("client-info", "clientInfo"),
        ("a.b", "aB"),
        ("a b", "aB"),
        ("", ""),
        ("_name", "name"),
        ("_", ""),
        ("a_1", "a_1"),
    ],
)
def test_to_camel_case(name: str, expected: str) -> None:
    assert to_camel_case(name) == expected


def test_casing_roundtrip() -> None:
    assert to_camel_case(to_snake_case("clientInfo")) == "clientInfo"


# --- from_dict: scalars / unions / literals / enums ------------------------


def test_from_dict_basic_types() -> None:
    assert from_dict(5, int) == 5
    assert from_dict("x", str) == "x"
    assert from_dict(True, bool) is True


def test_from_dict_value_of_another_type() -> None:
    with pytest.raises(TypeError) as error:
        from_dict("x", int)
    assert str(error.value) == "Value 'x' must be of type `<class 'int'>` but is `str`."


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (int | str | None, "int | str | None"),
        ((Literal["a"], int), "Literal['a'] | int"),
    ],
)
def test_from_dict_error_names_all_types(target: Any, expected: str) -> None:
    with pytest.raises(TypeError) as error:
        from_dict(1.5, target)
    assert str(error.value) == f"Value '1.5' must be of type `{expected}` but is `float`."


@pytest.mark.parametrize("target", [Any, None, ()])
def test_from_dict_any_or_no_target_keeps_the_value(target: Any) -> None:
    value = {"a": [1, {"b": None}]}
    assert from_dict(value, target) is value


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
    assert from_dict(1, int | None) == 1
    assert from_dict(None, int | None) is None


def test_from_dict_union() -> None:
    assert from_dict("x", (int, str)) == "x"


@pytest.mark.parametrize("target", [int | str, Union[int, str], (int, str)])
def test_from_dict_union_in_each_spelling(target: Any) -> None:
    assert from_dict(1, target) == 1


def test_from_dict_literal() -> None:
    assert from_dict("a", Literal["a", "b"]) == "a"
    with pytest.raises(TypeError):
        from_dict("c", Literal["a", "b"])


def test_from_dict_enum() -> None:
    assert from_dict("RED", Color) is Color.RED
    with pytest.raises(TypeError):
        from_dict("PURPLE", Color)


@pytest.mark.parametrize(("value", "target"), [(True, int), (False, int), (True, float), ([True], list[int])])
def test_from_dict_boolean_for_a_number(value: Any, target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict(value, target)


def test_from_dict_boolean_in_a_union_with_numbers() -> None:
    assert from_dict(True, int | float | bool) is True


def test_from_dict_number_for_bool() -> None:
    with pytest.raises(TypeError):
        from_dict(1, bool)


# --- from_dict: containers / dataclasses -----------------------------------


def test_from_dict_sequence_preserves_order_and_duplicates() -> None:
    assert from_dict([3, 1, 1, 2], list[int]) == [3, 1, 1, 2]


def test_from_dict_mapping() -> None:
    assert from_dict({"a": 1, "b": 2}, dict[str, int]) == {"a": 1, "b": 2}


@pytest.mark.parametrize(("value", "target"), [(["a"], list[int]), ({"a": "x"}, dict[str, int])])
def test_from_dict_wrong_element_of_a_container(value: Any, target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict(value, target)


def test_from_dict_array_for_a_dict_type() -> None:
    with pytest.raises(TypeError):
        from_dict([1], dict[str, int])


@pytest.mark.parametrize("document", ["[1]", b"[1]"])
def test_from_json_takes_text_or_bytes(document: Union[str, bytes]) -> None:
    assert from_json(document, list[int]) == [1]


def test_from_dict_dataclass_plain() -> None:
    assert from_dict({"x": 1, "y": 2}, Point) == Point(1, 2)


def test_from_dict_dataclass_camel_decoding() -> None:
    assert from_dict({"clientName": "bob", "retryCount": 3}, CamelInfo) == CamelInfo("bob", 3)


def test_from_dict_nested_dataclass() -> None:
    assert from_dict({"point": {"x": 1, "y": 2}}, HoldsPoint) == HoldsPoint(Point(1, 2))


def test_from_dict_class_with_annotated_fields_that_is_no_dataclass() -> None:
    result = from_dict({"a": 1}, AnnotatedClass)
    assert isinstance(result, AnnotatedClass)
    assert result.a == 1


def test_from_dict_required_field_without_a_key() -> None:
    with pytest.raises(TypeError):
        from_dict({"x": 1}, Point)


def test_from_dict_class_that_rejects_its_fields() -> None:
    with pytest.raises(TypeError, match=r"Can't initialize .*RejectsItsFields.* with parameters \{'a': 1\}: rejected"):
        from_dict({"a": 1}, RejectsItsFields)


def test_from_dict_class_with_more_of_the_keys_wins_in_any_order() -> None:
    assert from_dict({"a": 1, "b": 2, "c": 3}, (SimpleItem3, SimpleItem)) == SimpleItem3(1, 2, 3)


def test_from_dict_error_names_the_path_of_the_value() -> None:
    with pytest.raises(NamedTypeError) as error:
        from_dict({"a": {"x": "b", "y": 2}}, dict[str, Point])
    assert isinstance(error.value, TypeError)
    assert error.value.name == "a.x"
    assert str(error.value).startswith('Invalid value for "a.x": ')


def test_from_dict_ambiguous_union_raises() -> None:
    with pytest.raises(TypeError) as error:
        from_dict({"x": 1}, (A1, B1))
    assert str(error.value) == "Value {'x': 1} of type <class 'dict'> matches more than one of the types 'A1' | 'B1'."


# --- from_dict: a JSON object only becomes a class with fields --------------


@pytest.mark.parametrize("value", [{"q": 1}, {}])
@pytest.mark.parametrize("target", [float, complex])
def test_from_dict_object_for_a_number(value: Any, target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict(value, target)


@pytest.mark.parametrize("value", [{"q": 1}, {}])
@pytest.mark.parametrize("target", [list[int], tuple[int, str], Sequence[int], set[int]])
def test_from_dict_object_for_a_collection_that_is_no_mapping(value: Any, target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict(value, target)


@pytest.mark.parametrize("target", [float | None, list[int] | None, Point | float])
def test_from_dict_object_in_a_union_without_a_fitting_type(target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict({"q": 1}, target)


@pytest.mark.parametrize("target", [object, PlainClass])
def test_from_dict_object_for_a_class_without_fields(target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict({"q": 1}, target)


def test_from_dict_object_for_a_literal() -> None:
    with pytest.raises(TypeError) as error:
        from_dict({"a": 1}, Literal["a", "b"])
    assert str(error.value) == "Value '{'a': 1}' must be of type `typing.Literal['a', 'b']` but is `dict`."


def test_from_dict_object_for_a_class_with_fields_that_has_no_signature() -> None:
    with pytest.raises(TypeError):
        from_dict({"a": 1}, AnnotatedText)


def test_from_dict_object_in_a_union_with_a_fitting_dataclass() -> None:
    assert from_dict({"x": 1, "y": 2}, float | Point) == Point(1, 2)


# --- from_dict: abstract collection types ----------------------------------


@pytest.mark.parametrize(
    "target",
    [
        Sequence[int],
        MutableSequence[int],
        Collection[int],
        Iterable[int],
        Sequence,
        typing.Sequence[int],
        typing.Iterable[int],
    ],
)
def test_from_dict_abstract_collection_type_gives_a_list(target: Any) -> None:
    result = from_dict([1, 2], target)
    assert type(result) is list
    assert result == [1, 2]


def test_from_dict_wrong_element_of_an_abstract_collection_type() -> None:
    with pytest.raises(TypeError):
        from_dict(["a"], Sequence[int])


def test_from_dict_text_is_no_collection() -> None:
    with pytest.raises(TypeError):
        from_dict("abc", Sequence[str])


def test_from_dict_set_types_are_not_supported() -> None:
    with pytest.raises(TypeError, match=r"set\[int\]"):
        from_dict([1, 2], set[int])


# --- from_dict: tuples and named tuples -------------------------------------


def test_from_dict_tuple_fitting_list() -> None:
    assert from_dict([1, "a"], tuple[int, str]) == (1, "a")


def test_from_dict_tuple_wrong_type_at_a_position() -> None:
    with pytest.raises(TypeError):
        from_dict(["a", 1], tuple[int, str])


@pytest.mark.parametrize("value", [[1], [1, "a", 2]])
def test_from_dict_tuple_wrong_length(value: Any) -> None:
    with pytest.raises(TypeError):
        from_dict(value, tuple[int, str])


@pytest.mark.parametrize(("value", "expected"), [([1, 2], (1, 2)), ([], ())])
def test_from_dict_tuple_of_any_length(value: Any, expected: Any) -> None:
    assert from_dict(value, tuple[int, ...]) == expected


def test_from_dict_tuple_of_any_length_checks_its_elements() -> None:
    with pytest.raises(TypeError):
        from_dict(["a"], tuple[int, ...])


@pytest.mark.parametrize("target", [tuple, typing.Tuple])
def test_from_dict_tuple_without_arguments(target: Any) -> None:
    assert from_dict([1, "a"], target) == (1, "a")


def test_from_dict_subclass_of_tuple_keeps_its_type() -> None:
    result = from_dict([1, "a"], Tags)
    assert type(result) is Tags
    assert result == (1, "a")


def test_from_dict_tuple_in_a_union() -> None:
    assert from_dict([1, 5], Union[str, tuple[int, int]]) == (1, 5)


def test_from_dict_text_is_no_tuple() -> None:
    with pytest.raises(TypeError):
        from_dict("ab", tuple[str, str])


def test_from_dict_named_tuple_fitting_list() -> None:
    result = from_dict([1, "a"], Pair)
    assert type(result) is Pair
    assert result == Pair(1, "a")


def test_from_dict_named_tuple_wrong_type_at_a_position() -> None:
    with pytest.raises(TypeError):
        from_dict(["a", 1], Pair)


def test_from_dict_named_tuple_with_one_field() -> None:
    assert from_dict([1], One) == One(1)


def test_from_dict_named_tuple_fields_with_defaults() -> None:
    assert from_dict([1], Defaults) == Defaults(1, 0)


@pytest.mark.parametrize(("value", "target"), [([1, 2, 3], Defaults), ([1], Pair)])
def test_from_dict_named_tuple_wrong_length(value: Any, target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict(value, target)


def test_named_tuple_written_and_read_back() -> None:
    assert from_json(as_json(Pair(1, "a")), Pair) == Pair(1, "a")


def test_from_dict_object_for_a_named_tuple() -> None:
    assert from_dict({"x": 1, "y": "a"}, Pair) == Pair(1, "a")


def test_from_dict_named_tuple_without_types_takes_any_value() -> None:
    assert from_dict([1, "a"], Untyped) == Untyped(1, "a")


# --- from_dict: dict keys ---------------------------------------------------


@pytest.mark.parametrize("target", [dict[int, str], Mapping[int, str]])
def test_from_dict_key_of_the_wrong_type(target: Any) -> None:
    with pytest.raises(TypeError):
        from_dict({"a": "b"}, target)


def test_from_dict_number_as_a_string_is_no_number_key() -> None:
    with pytest.raises(TypeError):
        from_dict({"1": "b"}, dict[int, str])


def test_from_dict_key_of_the_key_type() -> None:
    assert from_dict({1: "b"}, dict[int, str]) == {1: "b"}


def test_from_dict_enum_as_a_key() -> None:
    assert from_dict({"first": 1}, dict[EnumData, int]) == {EnumData.FIRST: 1}


@pytest.mark.parametrize("target", [dict, dict[Any, Any]])
def test_from_dict_open_key_types(target: Any) -> None:
    assert from_dict({"a": 1}, target) == {"a": 1}


def test_from_dict_error_for_a_key_that_is_no_string_names_the_key() -> None:
    with pytest.raises(NamedTypeError) as error:
        from_dict({1: "b"}, dict[str, str])
    assert error.value.name == "1"


def test_from_dict_mapping_type_with_only_a_key_type() -> None:
    assert from_dict({"a": 1}, Counter[str]) == {"a": 1}


# --- from_dict: the values decide among classes with the same keys ----------


@pytest.mark.parametrize("target", [KindA | KindB, Union[KindB, KindA], (KindA, KindB)])
def test_from_dict_literal_tells_apart_classes_with_the_same_keys(target: Any) -> None:
    assert from_dict({"kind": "b", "value": 1}, target) == KindB("b", 1)
    assert from_dict({"kind": "a", "value": 1}, target) == KindA("a", 1)


def test_from_dict_type_of_a_value_tells_apart_classes_with_the_same_keys() -> None:
    assert from_dict({"x": "s"}, IntX | StrX) == StrX("s")
    assert from_dict({"x": 1}, IntX | StrX) == IntX(1)


def test_from_dict_classes_with_the_same_keys_inside_a_list() -> None:
    assert from_dict([{"kind": "b", "value": 1}, {"kind": "a", "value": 2}], list[KindA | KindB]) == [
        KindB("b", 1),
        KindA("a", 2),
    ]


def test_from_dict_no_class_with_the_same_keys_has_fitting_values() -> None:
    with pytest.raises(NamedTypeError) as error:
        from_dict({"kind": "c", "value": 1}, KindA | KindB)
    assert error.value.name == "kind"


def test_from_dict_several_classes_with_fitting_values_names_only_those() -> None:
    with pytest.raises(TypeError) as error:
        from_dict({"x": 1}, (A1, StrX, B1))
    assert str(error.value) == "Value {'x': 1} of type <class 'dict'> matches more than one of the types 'A1' | 'B1'."


def test_from_dict_tie_of_classes_with_fewer_keys_does_not_count() -> None:
    assert from_dict({"a": 1, "b": 2, "c": 3}, (SimpleItem, ItemAB, SimpleItem3)) == SimpleItem3(1, 2, 3)


def test_from_dict_class_without_all_its_required_keys_does_not_count_for_more_keys() -> None:
    assert from_dict({"a": 1, "b": 2}, (SimpleItem3, ItemA)) == ItemA(1)


# --- from_dict: a class goes before a dict type -----------------------------


@pytest.mark.parametrize("target", [Point | dict[str, Any], dict[str, Any] | Point, Union[dict[str, Any], Point]])
def test_from_dict_class_that_knows_all_keys_goes_before_a_dict_type(target: Any) -> None:
    assert from_dict({"x": 1, "y": 2}, target) == Point(1, 2)


@pytest.mark.parametrize("target", [Point | dict[str, Any], dict[str, Any] | Point])
def test_from_dict_unknown_key_keeps_the_dict(target: Any) -> None:
    assert from_dict({"x": 1, "y": 2, "z": 3}, target) == {"x": 1, "y": 2, "z": 3}


def test_from_dict_wrong_value_for_the_class_keeps_the_dict() -> None:
    assert from_dict({"x": "s", "y": 2}, Point | dict[str, Any]) == {"x": "s", "y": 2}


def test_from_dict_missing_required_key_keeps_the_dict() -> None:
    assert from_dict({"x": 1}, Point | dict[str, Any]) == {"x": 1}


def test_from_dict_several_classes_that_fit_keep_the_dict() -> None:
    assert from_dict({"x": 1}, (A1, B1, dict[str, Any])) == {"x": 1}


def test_from_dict_dict_type_that_does_not_fit_leaves_the_class() -> None:
    assert from_dict({"x": 1, "y": 2, "z": "s"}, Point | dict[str, int]) == Point(1, 2)


def test_from_dict_dict_type_alone_gives_the_dict() -> None:
    assert from_dict({"x": 1, "y": 2}, dict[str, int]) == {"x": 1, "y": 2}


def test_from_dict_strict_counts_an_empty_key_as_unknown() -> None:
    with pytest.raises(TypeError):
        from_dict({"x": 1, "y": 2, "": 3}, Point, strict=True)


# --- from_dict: a union tries its other types ------------------------------


def test_from_dict_union_of_list_types() -> None:
    assert from_dict(["a"], list[int] | list[str]) == ["a"]


def test_from_dict_union_of_tuple_types() -> None:
    assert from_dict(["a", 1], tuple[int, str] | tuple[str, int]) == ("a", 1)


def test_from_dict_union_of_dict_types_with_classes() -> None:
    assert from_dict({"x": {"b": 1}}, dict[str, UA] | dict[str, UB]) == {"x": UB(1)}


def test_from_dict_union_of_a_dict_type_and_a_class() -> None:
    assert from_dict({"a": "x"}, dict[str, int] | UA | dict[str, str]) == {"a": "x"}


def test_from_dict_union_wrong_length_goes_on_to_the_next_type() -> None:
    assert from_dict([1], tuple[int, str] | list[int]) == [1]


def test_from_dict_union_without_a_fitting_type_fails_with_the_first_error() -> None:
    with pytest.raises(NamedTypeError) as error:
        from_dict({"a": {"x": "b", "y": 2}}, dict[str, Point] | None)
    assert error.value.name == "a.x"


def test_from_dict_union_of_containers_without_a_fitting_type_names_the_element() -> None:
    with pytest.raises(TypeError) as error:
        from_dict(["a"], list[int] | list[float])
    assert str(error.value) == "Value 'a' must be of type `<class 'int'>` but is `str`."


@pytest.mark.parametrize("target", [Optional[TypingUnionItem], Union[TypingUnionItem, int]])
def test_from_dict_union_of_typing_fails_with_the_first_error(target: Any) -> None:
    with pytest.raises(NamedTypeError) as error:
        from_dict({"x": "b"}, target)
    assert error.value.name == "x"
    assert error.value.message == "Value 'b' must be of type `<class 'int'>` but is `str`."


def test_from_dict_union_of_typing_with_a_dict_type_fails_with_the_first_error() -> None:
    with pytest.raises(NamedTypeError) as error:
        from_dict({"a": "b"}, Optional[Dict[str, int]])
    assert error.value.name == "a"


def test_from_dict_field_with_a_union_of_typing_names_the_path() -> None:
    with pytest.raises(NamedTypeError) as error:
        from_dict({"item": {"x": "b"}}, HoldsTypingUnion)
    assert error.value.name == "item.x"


# --- as_dict / as_json -----------------------------------------------------


def test_as_dict_plain() -> None:
    assert as_dict(Point(1, 2)) == {"x": 1, "y": 2}


def test_as_dict_camel_encoding() -> None:
    assert as_dict(CamelInfo("bob", 3)) == {"clientName": "bob", "retryCount": 3}


def test_as_json_camel_encoding() -> None:
    assert as_json(CamelInfo("bob", 3)) == '{"clientName": "bob", "retryCount": 3}'


def test_as_dict_without_encoding_uses_the_names_of_the_fields() -> None:
    assert as_dict(CamelInfo("bob", 3), encode=False) == {"client_name": "bob", "retry_count": 3}


def test_as_dict_uses_the_alias() -> None:
    assert as_dict(SimpleItemWithAlias(2)) == {"a_test": 2}


def test_as_dict_enum_value() -> None:
    assert as_dict(HasColor(Color.RED)) == {"c": "RED"}


def test_as_json_roundtrip() -> None:
    p = Point(3, 4)
    assert from_json(as_json(p), Point) == p


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ((1, 2), "[1, 2]"),
        (Pair(1, "a"), '[1, "a"]'),
        ({1}, "[1]"),
    ],
)
def test_as_json_writes_collections_as_arrays(value: Any, expected: str) -> None:
    assert as_json(value) == expected


def test_as_json_writes_a_frozenset_as_an_array() -> None:
    assert as_json(frozenset({1})) == "[1]"


def test_as_json_writes_the_value_of_an_enum_member() -> None:
    assert as_json(EnumData.FIRST) == '"first"'
    assert as_json(Color.RED) == '"RED"'


def test_as_json_keeps_text_outside_ascii() -> None:
    assert as_json("\u00e4") == '"\u00e4"'


def test_as_json_value_that_json_cannot_hold() -> None:
    with pytest.raises(TypeError) as error:
        as_json(b"x")
    assert str(error.value) == "Can't get default value for <class 'bytes'> with value b'x'"


@dataclass
class _Measure:
    value: float


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize(
    "wrap", [lambda n: n, lambda n: [1, n], _Measure], ids=["alone", "in a list", "in a dataclass"]
)
def test_as_json_fails_for_floats_that_json_does_not_allow(number: float, wrap: Callable[[float], Any]) -> None:
    # JSON has no NaN or Infinity; a peer that reads JSON strictly could not read the message.
    with pytest.raises(ValueError, match="not JSON compliant"):
        as_json(wrap(number))


def test_as_json_leaves_out_fields_by_their_metadata_and_none_with_a_default() -> None:
    assert json.loads(as_json(FieldsWithMetadata())) == {"plain": 1, "no_init_forced": "f"}


def test_as_dict_requires_a_dataclass() -> None:
    with pytest.raises(TypeError) as error:
        as_dict(5)
    assert str(error.value) == "as_dict() should be called on dataclass instances"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Point(1, 2), {"x": 1, "y": 2}),
        ((1, 2), [1, 2]),
        (Pair(1, "a"), [1, "a"]),
        ({1}, [1]),
        (frozenset({1}), [1]),
        ({"a": (1, 2)}, {"a": [1, 2]}),
        (Color.RED, "RED"),
        (None, None),
    ],
)
def test_as_dict_writes_plain_values(value: Any, expected: Any) -> None:
    assert as_dict(HoldsAny(value)) == {"value": expected}


def test_as_dict_writes_every_field_whatever_its_metadata() -> None:
    assert as_dict(FieldsWithMetadata()) == {
        "plain": 1,
        "not_saved": "s",
        "no_init": "h",
        "no_init_forced": "f",
        "maybe": None,
    }


def test_as_dict_writes_the_repr_of_an_unknown_type_with_a_warning() -> None:
    with pytest.warns(UserWarning, match=r"<class 'bytes'> with value b'x'"):
        result = as_dict(HoldsAny(b"x"))
    assert result == {"value": "b'x'"}


def test_as_dict_remove_defaults_leaves_out_a_value_from_default() -> None:
    assert as_dict(SimpleItemWithOnlyOptionalFields(1, 3), remove_defaults=True) == {"b": 3}


def test_as_dict_remove_defaults_leaves_out_a_value_from_default_factory() -> None:
    assert as_dict(WithFactory(), remove_defaults=True) == {}
    assert as_dict(WithFactory(["x"]), remove_defaults=True) == {"tags": ["x"]}


def test_as_dict_remove_defaults_writes_a_field_without_a_default() -> None:
    assert as_dict(SimpleItemWithOptionalField(None), remove_defaults=True) == {"a": None}


def test_as_dict_remove_defaults_in_a_nested_dataclass() -> None:
    value = HoldsAny(SimpleItemWithOnlyOptionalFields(a=5))
    assert as_dict(value, remove_defaults=True) == {"value": {"a": 5}}


# --- ValidateMixin ---------------------------------------------------------


def test_validate_mixin_accepts_valid() -> None:
    assert Validated(5).n == 5


def test_validate_mixin_rejects_invalid() -> None:
    with pytest.raises(TypeValidationError):
        Validated("not an int")  # type: ignore[arg-type]


def test_validate_mixin_does_nothing_for_a_class_that_is_no_dataclass() -> None:
    class NoDataclass(ValidateMixin):
        pass

    NoDataclass().__post_init__()


@pytest.mark.parametrize("cls", [ConvertedByFunction, ConvertedByMethod])
def test_validate_mixin_applies_the_convert_metadata(cls: Any) -> None:
    assert cls("5").n == 5


def test_validate_mixin_applies_the_validate_metadata() -> None:
    assert CheckedByFunction(1).n == 1
    with pytest.raises(TypeValidationError) as error:
        CheckedByFunction(-1)
    assert error.value.errors == {"n": ["negative"]}


def test_type_validation_error_names_the_class_and_the_errors() -> None:
    with pytest.raises(TypeValidationError) as error:
        CheckedByFunction(-1)
    name = f"{CheckedByFunction.__module__}.CheckedByFunction"
    assert str(error.value) == f"{name} (errors = {{'n': ['negative']}})"
    assert repr(error.value) == f"{name}('Dataclass Type Validation Error', errors={{'n': ['negative']}})"


# --- validate_types --------------------------------------------------------


def _run_in_a_new_process(code: str) -> str:
    # The caches of the module take `int | str` and `Union[int, str]` as the same key, so an
    # earlier test in this process could hide a difference between the two spellings.
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_validate_types_union_as_the_first_call_in_a_process() -> None:
    output = _run_in_a_new_process(
        """
        from jsonrpcpeer.json_helpers import validate_types

        print(validate_types(int | str, 5))
        """
    )
    assert output == "[]"


@pytest.mark.parametrize("target", [int | str, Union[int, str], (int, str)])
def test_validate_types_value_in_a_union(target: Any) -> None:
    assert validate_types(target, 5) == []


def test_validate_types_value_outside_a_union() -> None:
    target: Any = int | str
    errors = validate_types(target, 1.5)
    assert len(errors) == 1
    assert all(name in errors[0] for name in ("int", "str", "float"))


def test_validate_mixin_field_with_a_union_as_the_first_use_in_a_process() -> None:
    output = _run_in_a_new_process(
        """
        from dataclasses import dataclass

        from jsonrpcpeer.json_helpers import TypeValidationError, ValidateMixin


        @dataclass
        class Holder(ValidateMixin):
            n: int | None


        print(Holder(3).n)
        print(Holder(None).n)
        try:
            Holder("x")
        except TypeValidationError:
            print("rejected")
        """
    )
    assert output.split() == ["3", "None", "rejected"]


def test_validate_types_element_of_a_list() -> None:
    assert validate_types(list[int], [1]) == []
    assert validate_types(list[int], ["a"]) == ["Expected type <class 'int'> but got <class 'str'>"]


def test_validate_types_key_and_value_of_a_dict() -> None:
    assert validate_types(dict[str, int], {"a": 1}) == []
    assert validate_types(dict[str, int], {1: "a"}) == [
        "Expected type <class 'str'> but got <class 'int'>",
        "Expected type <class 'int'> but got <class 'str'>",
    ]


def test_validate_types_literal() -> None:
    target: Any = Literal["a"]
    assert validate_types(target, "a") == []
    assert validate_types(target, "b") == ["Value b is not in ('a',)"]


def test_validate_types_takes_a_boolean_for_int() -> None:
    assert validate_types(int, True) == []


@pytest.mark.parametrize("target", [None, Any])
def test_validate_types_no_type_or_any(target: Any) -> None:
    assert validate_types(target, 1) == []


def test_validate_types_positions_of_a_tuple() -> None:
    assert validate_types(tuple[int, str], (1, "a")) == []
    assert validate_types(tuple[int, str], ("a", 1)) == [
        "Expected type <class 'int'> but got <class 'str'>",
        "Expected type <class 'str'> but got <class 'int'>",
    ]


def test_validate_types_length_of_a_tuple() -> None:
    assert validate_types(tuple[int, str], (1,)) == ["Expected 2 values for type tuple[int, str] but got 1"]


def test_validate_types_tuple_of_any_length() -> None:
    assert validate_types(tuple[int, ...], (1, 2)) == []
    assert validate_types(tuple[int, ...], ("a",)) == ["Expected type <class 'int'> but got <class 'str'>"]


def test_validate_types_takes_a_list_for_a_tuple_type() -> None:
    assert validate_types(tuple[int, str], [1, "a"]) == []
    assert validate_types(tuple[int, str], ["a", 1]) != []


def test_validate_types_text_is_no_tuple() -> None:
    assert validate_types(tuple[str, str], "ab") == ["Expected type tuple[str, str] but got <class 'str'>"]


# The sections named RobotCode come from the tests of RobotCode's copy of this module
# (tests/robotcode/core/test_dataclasses.py), with their names and dataclasses.


# --- RobotCode: as_json ----------------------------------------------------


class EnumData(Enum):
    FIRST = "first"
    SECOND = "second"


@pytest.mark.parametrize(
    ("expr", "expected", "indent", "compact"),
    [
        (1, "1", None, None),
        (True, "true", None, None),
        (False, "false", None, None),
        ("Test", '"Test"', None, None),
        ([], "[]", None, None),
        (["Test"], '["Test"]', None, None),
        (["Test", 1], '["Test", 1]', None, None),
        ({}, "{}", None, None),
        ({"a": 1}, '{"a": 1}', None, None),
        ({"a": 1}, '{\n    "a": 1\n}', True, None),
        ({"a": 1, "b": True}, '{\n    "a": 1,\n    "b": true\n}', True, None),
        ({"a": 1, "b": True}, '{"a":1,"b":true}', None, True),
        ((), "[]", None, None),
        ((1, 2, 3), "[1, 2, 3]", None, None),
        (set(), "[]", None, None),
        ({1, 2}, "[1, 2]", None, None),
        ([EnumData.FIRST, EnumData.SECOND], '["first", "second"]', None, None),
    ],
)
def test_encode_simple(expr: Any, expected: str, indent: Optional[bool], compact: Optional[bool]) -> None:
    assert as_json(expr, indent, compact) == expected


@dataclass
class SimpleItem:
    a: int
    b: int


def test_encode_simple_dataclass() -> None:
    assert as_json(SimpleItem(1, 2)) == '{"a": 1, "b": 2}'


@dataclass
class ComplexItem:
    list_field: List[Any]
    dict_field: Dict[Any, Any]


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        (ComplexItem([], {}), '{"list_field": [], "dict_field": {}}'),
        (
            ComplexItem([1, "2", 3], {"a": "hello", 1: True}),
            '{"list_field": [1, "2", 3], "dict_field": {"a": "hello", "1": true}}',
        ),
    ],
)
def test_encode_complex_dataclass(expr: Any, expected: str) -> None:
    assert as_json(expr) == expected


@dataclass
class ComplexItemWithConfigEncodeCase(ComplexItem):
    @classmethod
    def _encode_case(cls, s: str) -> str:
        return to_camel_case(s)

    @classmethod
    def _decode_case(cls, s: str) -> str:
        return to_snake_case(s)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        (
            ComplexItemWithConfigEncodeCase([], {}),
            '{"listField": [], "dictField": {}}',
        ),
        (
            ComplexItemWithConfigEncodeCase([1, "2", 3], {"a": "hello", 1: True}),
            '{"listField": [1, "2", 3], "dictField": {"a": "hello", "1": true}}',
        ),
    ],
)
def test_encode_complex_dataclass_with_config_encode_case(expr: Any, expected: str) -> None:
    assert as_json(expr) == expected


@dataclass
class SimpleItemWithOptionalField:
    a: Optional[int]


def test_encode_with_optional_field() -> None:
    assert as_json(SimpleItemWithOptionalField(1)) == '{"a": 1}'
    assert as_json(SimpleItemWithOptionalField(None)) == '{"a": null}'


@dataclass
class SimpleItemWithOptionalFieldAndNoneAsDefaultValue:
    a: Optional[int] = None


def test_encode_with_optional_field_and_none_as_default_value() -> None:
    assert as_json(SimpleItemWithOptionalFieldAndNoneAsDefaultValue(1)) == '{"a": 1}'
    assert as_json(SimpleItemWithOptionalFieldAndNoneAsDefaultValue(None)) == "{}"


# --- RobotCode: from_json, values ------------------------------------------


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ("1", int, 1),
        ('"str"', str, "str"),
        ("1.0", float, 1.0),
        ("true", bool, True),
        ("false", bool, False),
        ('"str"', (str, int), "str"),
        ("1", (int, str), 1),
        ("[]", (int, str, List[int]), []),
        ("[1]", (int, List[int]), [1]),
        ("1", Any, 1),
        ("[]", Union[int, str, List[int]], []),
        ('"first"', EnumData, EnumData.FIRST),
        ('"second"', EnumData, EnumData.SECOND),
        (
            '["first", "second"]',
            List[EnumData],
            [EnumData.FIRST, EnumData.SECOND],
        ),
        (
            '["first", "second", "ninety"]',
            List[Union[EnumData, str]],
            [EnumData.FIRST, EnumData.SECOND, "ninety"],
        ),
        ('"warn"', Literal["warn"], "warn"),
        ('["warn"]', List[Literal["warn", "error"]], ["warn"]),
        ('["warn", "error"]', List[Literal["warn", "error"]], ["warn", "error"]),
    ],
)
def test_decode_simple(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ("{}", dict, {}),
        ('{"a": 1}', dict, {"a": 1}),
        ('{"a": 1}', Dict[str, int], {"a": 1}),
        ('{"a": 1, "b": 2}', Dict[str, int], {"a": 1, "b": 2}),
        (
            '{"a": 1, "b": null}',
            Dict[str, Union[int, str, None]],
            {"a": 1, "b": None},
        ),
        (
            '{"a": {}, "b": {"a": 2}}',
            Dict[str, Dict[str, Any]],
            {"a": {}, "b": {"a": 2}},
        ),
    ],
)
def test_decode_dict(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


# --- RobotCode: from_json, classes -----------------------------------------


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ('{"a": 1, "b": 2}', SimpleItem, SimpleItem(1, 2)),
        ('{"b": 2, "a": 1}', SimpleItem, SimpleItem(1, 2)),
        ('{"b": 2, "a": 1}', Optional[SimpleItem], SimpleItem(1, 2)),
    ],
)
def test_decode_simple_class(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


def test_decode_optional_simple_class() -> None:
    assert from_json("null", Optional[SimpleItem]) is None

    with pytest.raises(TypeError):
        assert from_json("null", SimpleItem) is None


@dataclass
class SimpleItemWithNoFields:
    pass


def test_decode_with_no_fields() -> None:
    assert from_json("{}", SimpleItemWithNoFields) == SimpleItemWithNoFields()


@dataclass
class SimpleItemWithOnlyOptionalFields:
    a: int = 1
    b: int = 2


def test_decode_with_only_optional_fields() -> None:
    assert from_json("{}", SimpleItemWithOnlyOptionalFields) == SimpleItemWithOnlyOptionalFields()


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        (
            '{"listField": [], "dictField": {}}',
            ComplexItemWithConfigEncodeCase,
            ComplexItemWithConfigEncodeCase([], {}),
        ),
        (
            '{"listField": [1,2], "dictField": {"a": 1, "b": "2"}}',
            ComplexItemWithConfigEncodeCase,
            ComplexItemWithConfigEncodeCase([1, 2], {"a": 1, "b": "2"}),
        ),
    ],
)
def test_decode_complex_class_with_encoding(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


@dataclass
class SimpleItemWithOptionalFields:
    first: int
    second: bool = True
    third: Optional[str] = None
    forth: Optional[float] = None


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        (
            '{"first": 1}',
            SimpleItemWithOptionalFields,
            SimpleItemWithOptionalFields(first=1),
        ),
        (
            '{"first": 1, "third": "Hello"}',
            SimpleItemWithOptionalFields,
            SimpleItemWithOptionalFields(first=1, third="Hello"),
        ),
        (
            '{"first": 1, "forth": 1.0}',
            SimpleItemWithOptionalFields,
            SimpleItemWithOptionalFields(first=1, forth=1.0),
        ),
    ],
)
def test_decode_simple_item_with_optional_field(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


# --- RobotCode: from_json, unions of classes -------------------------------


@dataclass
class SimpleItem1:
    d: int
    e: int
    f: int = 1


@dataclass
class ComplexItemWithUnionType:
    a_union_field: Union[SimpleItem, SimpleItem1]


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        (
            '{"a_union_field":{"a":1, "b":2}}',
            ComplexItemWithUnionType,
            ComplexItemWithUnionType(SimpleItem(1, 2)),
        ),
        (
            '{"a_union_field":{"d":1, "e":2}}',
            ComplexItemWithUnionType,
            ComplexItemWithUnionType(SimpleItem1(1, 2)),
        ),
        (
            '{"a_union_field":{"d":1, "e":2, "f": 3}}',
            ComplexItemWithUnionType,
            ComplexItemWithUnionType(SimpleItem1(1, 2, 3)),
        ),
    ],
)
def test_decode_with_union_and_different_keys(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


@dataclass
class SimpleItem2:
    a: int
    b: int
    c: int = 1


@dataclass
class ComplexItemWithUnionTypeWithSameProperties:
    a_union_field: Union[SimpleItem, SimpleItem2]


def test_decode_with_union_and_some_same_keys() -> None:
    assert from_json(
        '{"a_union_field": {"a": 1, "b":2, "c":3}}',
        ComplexItemWithUnionTypeWithSameProperties,
    ) == ComplexItemWithUnionTypeWithSameProperties(SimpleItem2(1, 2, 3))


def test_decode_with_union_and_same_keys_should_raise_typeerror() -> None:
    with pytest.raises(TypeError):
        from_json(
            '{"a_union_field": {"a": 1, "b":2}}',
            ComplexItemWithUnionTypeWithSameProperties,
        )


def test_decode_with_union_and_no_keys_should_raise_typeerror() -> None:
    with pytest.raises(TypeError):
        from_json('{"a_union_field": {}}', ComplexItemWithUnionTypeWithSameProperties)


def test_decode_with_union_and_no_match_should_raise_typeerror() -> None:
    with pytest.raises(TypeError):
        from_json(
            '{"a_union_field": {"x": 1, "y":2}}',
            ComplexItemWithUnionTypeWithSameProperties,
        )


@dataclass
class SimpleItem3:
    a: int
    b: int
    c: int


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ('{"a":1, "b": 2}', (SimpleItem, SimpleItem3), SimpleItem(1, 2)),
        (
            '{"a":1, "b": 2, "c": 3}',
            (SimpleItem, SimpleItem3),
            SimpleItem3(1, 2, 3),
        ),
    ],
)
def test_decode_with_some_same_fields(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


def test_decode_with_some_unambigous_fields_should_raise_typeerror() -> None:
    with pytest.raises(TypeError):
        from_json('{"a":1, "b": 2}', (SimpleItem, SimpleItem2))


@dataclass
class ComplexItemWithUnionTypeWithSimpleAndComplexTypes:
    a_union_field: Union[bool, SimpleItem, SimpleItem1]


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        (
            '{"a_union_field": true}',
            ComplexItemWithUnionTypeWithSimpleAndComplexTypes,
            ComplexItemWithUnionTypeWithSimpleAndComplexTypes(True),
        ),
        (
            '{"a_union_field": {"a":1, "b":2}}',
            ComplexItemWithUnionTypeWithSimpleAndComplexTypes,
            ComplexItemWithUnionTypeWithSimpleAndComplexTypes(SimpleItem(1, 2)),
        ),
    ],
)
def test_decode_union_with_simple_and_complex_types(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


def test_decode_union_with_unknown_keys_should_raise_typeerror() -> None:
    with pytest.raises(TypeError):
        from_json(
            '{"a_union_field": {"d":1, "ef":2}}',
            ComplexItemWithUnionTypeWithSimpleAndComplexTypes,
        ) == ComplexItemWithUnionTypeWithSimpleAndComplexTypes(SimpleItem(1, 2))


# --- RobotCode: from_json, strict mode -------------------------------------


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ('{"a":1, "b":2, "c":3}', SimpleItem, SimpleItem(1, 2)),
        (
            '{"a":1, "b":2, "c":3}',
            SimpleItemWithOnlyOptionalFields,
            SimpleItemWithOnlyOptionalFields(1, 2),
        ),
        (
            '{"a":1}',
            SimpleItemWithOnlyOptionalFields,
            SimpleItemWithOnlyOptionalFields(1),
        ),
        (
            "{}",
            SimpleItemWithOnlyOptionalFields,
            SimpleItemWithOnlyOptionalFields(),
        ),
        ("{}", SimpleItemWithNoFields, SimpleItemWithNoFields()),
        ('{"a": 1}', SimpleItemWithNoFields, SimpleItemWithNoFields()),
        (
            '{"a":1, "b":2, "c": 3}',
            (SimpleItemWithNoFields, SimpleItem),
            SimpleItem(1, 2),
        ),
    ],
)
def test_decode_non_strict_should_work(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ('{"a":1, "b":2}', SimpleItem, SimpleItem(1, 2)),
        (
            '{"a":1, "b":2}',
            SimpleItemWithOnlyOptionalFields,
            SimpleItemWithOnlyOptionalFields(1, 2),
        ),
        (
            '{"a":1}',
            SimpleItemWithOnlyOptionalFields,
            SimpleItemWithOnlyOptionalFields(1),
        ),
        (
            "{}",
            SimpleItemWithOnlyOptionalFields,
            SimpleItemWithOnlyOptionalFields(),
        ),
        ("{}", SimpleItemWithNoFields, SimpleItemWithNoFields()),
        ("{}", (SimpleItemWithNoFields, SimpleItem), SimpleItemWithNoFields()),
        (
            '{"a":1, "b":2}',
            (SimpleItemWithNoFields, SimpleItem),
            SimpleItem(1, 2),
        ),
    ],
)
def test_decode_strict_should_work(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type, strict=True) == expected


@pytest.mark.parametrize(
    ("expr", "type"),
    [
        ('{"a":1, "b": 2, "c": 3}', SimpleItem),
        ('{"a":1, "b": 2, "c": 3}', SimpleItemWithOnlyOptionalFields),
        ('{"a":1, "c": 3}', SimpleItemWithOnlyOptionalFields),
        ('{"c": 3}', SimpleItemWithOnlyOptionalFields),
        ('{"c": 3}', SimpleItemWithNoFields),
    ],
)
def test_decode_strict_with_invalid_data_should_raise_typeerror(expr: Any, type: Any) -> None:
    with pytest.raises(TypeError):
        from_json(expr, type, strict=True)


# --- RobotCode: literals, empty objects, aliases ---------------------------


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ('"test"', Literal["test", "blah", "bluff"], "test"),
        ('"bluff"', Literal["test", "blah", "bluff"], "bluff"),
        ('"dada"', (Literal["test", "blah", "bluff"], str), "dada"),
        ("1", (Literal["test", "blah", "bluff"], int), 1),
    ],
)
def test_literal_should_work(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type) == expected


@pytest.mark.parametrize(
    ("expr", "type"),
    [
        ('"dada"', Literal["test", "blah", "bluff"]),
        ('"dada"', (Literal["test", "blah", "bluff"], int)),
    ],
)
def test_literal_with_invalid_args_should_raise_typerror(expr: Any, type: Any) -> None:
    with pytest.raises(TypeError):
        from_json(expr, type)


@dataclass
class SimpleData:
    a: Optional[int] = None
    b: Optional[str] = None


@dataclass
class ComplexData:
    data: Optional[SimpleData] = None
    more_data: Optional[str] = None


@pytest.mark.parametrize(
    ("expr", "type", "expected"),
    [
        ('{"a":1, "b":"2"}', Optional[SimpleData], SimpleData(1, "2")),
        ("{}", Optional[SimpleData], SimpleData()),
        ("{}", Optional[ComplexData], ComplexData()),
    ],
)
def test_empty_dict_should_not_match_none_type(expr: Any, type: Any, expected: str) -> None:
    assert from_json(expr, type, strict=True) == expected


@dataclass
class SimpleItemWithAlias:
    a: int = field(metadata={"alias": "a_test"})


def test_encode_decode_with_field_alias_should_work() -> None:
    assert from_json('{"a_test": 2}', SimpleItemWithAlias) == SimpleItemWithAlias(2)
    assert as_json(SimpleItemWithAlias(2)) == '{"a_test": 2}'


@dataclass
class CamelLeaf(CamelSnakeMixin):
    leaf_name: str
    leaf_value: Optional[int] = None


@dataclass
class CamelBranch(CamelSnakeMixin):
    branch_name: str
    leaf_count: int


@dataclass
class CamelTree(CamelSnakeMixin):
    tree_kind: EnumData
    trace_level: Literal["off", "verbose"]
    all_leaves: List[CamelLeaf]
    extra_options: Dict[str, Any]
    main_item: Union[CamelLeaf, CamelBranch]
    parent_tree: Optional["CamelTree"] = None
    display_name: Optional[str] = None


def test_nested_dataclasses_in_camel_case_round_trip() -> None:
    # In place of RobotCode's test_really_complex_data, which needs its LSP types.
    tree = CamelTree(
        tree_kind=EnumData.SECOND,
        trace_level="verbose",
        all_leaves=[CamelLeaf("a", 1), CamelLeaf("b")],
        extra_options={"some_key": [1, {"nested_key": True}]},
        main_item=CamelBranch("c", 2),
        parent_tree=CamelTree(
            tree_kind=EnumData.FIRST,
            trace_level="off",
            all_leaves=[],
            extra_options={},
            main_item=CamelLeaf("d"),
        ),
    )

    text = as_json(tree)

    assert json.loads(text) == {
        "treeKind": "second",
        "traceLevel": "verbose",
        "allLeaves": [{"leafName": "a", "leafValue": 1}, {"leafName": "b"}],
        "extraOptions": {"some_key": [1, {"nested_key": True}]},
        "mainItem": {"branchName": "c", "leafCount": 2},
        "parentTree": {
            "treeKind": "first",
            "traceLevel": "off",
            "allLeaves": [],
            "extraOptions": {},
            "mainItem": {"leafName": "d"},
        },
    }
    assert from_json(text, CamelTree) == tree
