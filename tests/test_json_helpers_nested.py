"""The JSON conversion in combinations: a realistic nested model, and random nested types from Hypothesis.

tests/test_json_helpers.py goes through each branch of the module, but a fault can hide in what the branches do
together. These tests go through deep combinations, in both directions and with wrong values.

On CI, Hypothesis uses the same examples on each run. Locally it draws new ones, and keeps those that failed in
.hypothesis/ to try them first next time.
"""

# String annotations on purpose: from_dict has to resolve them, the forward references too.
from __future__ import annotations

import dataclasses
import functools
import json
import operator
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Tuple, Union

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from jsonrpcpeer.json_helpers import CamelSnakeMixin, NamedTypeError, as_dict, as_json, from_dict, from_json


def _same(a: Any, b: Any) -> bool:
    """Equal, and of the same types at every level, because `1 == 1.0 == True`."""
    if type(a) is not type(b):
        return False
    if dataclasses.is_dataclass(a):
        return all(_same(getattr(a, f.name), getattr(b, f.name)) for f in dataclasses.fields(a))
    if isinstance(a, dict):
        return _same(list(a), list(b)) and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return bool(a == b)


# --- a realistic nested model ------------------------------------------------


class Status(Enum):
    PASS = "pass"
    FAIL = "fail"


class Level(str, Enum):
    INFO = "info"
    WARN = "warn"


class Priority(IntEnum):
    LOW = 10
    HIGH = 20


class Span(NamedTuple):
    start: float
    end: float


@dataclass
class Started:
    kind: Literal["started"]
    at: float


@dataclass
class Stopped:
    kind: Literal["stopped"]
    at: float


@dataclass
class Tag(CamelSnakeMixin):
    tag_name: str
    tag_value: Optional[str] = None


@dataclass
class Message(CamelSnakeMixin):
    message_text: str
    log_level: Level = Level.INFO
    is_html: bool = False


@dataclass
class Passed(CamelSnakeMixin):
    passed_at: float


@dataclass
class Failed(CamelSnakeMixin):
    failure_message: str
    trace_lines: List[str] = field(default_factory=list)


@dataclass
class Skipped(CamelSnakeMixin):
    skip_reason: str


@dataclass
class Keyword(CamelSnakeMixin):
    kw_name: str
    kw_args: List[Union[int, str, float, bool, List[Any], Dict[str, Any], None]] = field(default_factory=list)
    child_keywords: List[Keyword] = field(default_factory=list)
    log_messages: list[Message] = field(default_factory=list)
    kw_status: Status = Status.PASS
    time_span: Span | None = None


@dataclass
class Case(CamelSnakeMixin):
    case_name: str
    case_tags: List[Tag]
    setup_keyword: Optional[Keyword]
    case_body: Sequence[Keyword]
    meta_data: Dict[str, Union[str, int, List[str], Dict[str, List[int]]]]
    case_result: Union[Passed, Failed, Skipped]
    priority: Priority = Priority.LOW
    retries: Tuple[int, ...] = ()


@dataclass
class Suite(CamelSnakeMixin):
    suite_name: str
    sub_suites: List[Suite]
    suite_cases: Mapping[str, Case]
    stats_table: Dict[str, Dict[str, int]]
    parent_suite: Optional[Suite] = None
    all_spans: Tuple[Span, ...] = ()
    tagged_pairs: Optional[Dict[str, Tuple[int, List[Optional[Tag]]]]] = None
    last_event: Union[Started, Stopped, None] = None
    last_details: Union[Dict[str, Any], Tag, None] = None
    free_payload: Any = None


def _keyword(depth: int, width: int) -> Keyword:
    return Keyword(
        kw_name=f"keyword {depth}",
        kw_args=[1, "two", 3.5, True, None, [1, [2, {"x": [3]}]], {"deep": {"er": [{"est": None}]}}],
        child_keywords=[_keyword(depth - 1, width) for _ in range(width)] if depth else [],
        log_messages=[Message("hello"), Message("<b>bold</b>", Level.WARN, True)],
        kw_status=Status.FAIL if depth % 2 else Status.PASS,
        time_span=Span(1.5, 2.5) if depth % 3 else None,
    )


def _suite(depth: int) -> Suite:
    case = Case(
        case_name="case",
        case_tags=[Tag("a"), Tag("b", "c")],
        setup_keyword=_keyword(1, 1),
        case_body=[_keyword(3, 2)],
        meta_data={"text": "x", "number": 1, "list": ["x"], "dict": {"k": [1, 2]}},
        case_result=Failed("boom", ["line 1", "line 2"]),
        priority=Priority.HIGH,
        retries=(1, 2, 3),
    )
    return Suite(
        suite_name=f"suite {depth}",
        sub_suites=[_suite(depth - 1) for _ in range(2)] if depth else [],
        suite_cases={
            "failed": case,
            "passed": dataclasses.replace(case, case_result=Passed(1.5), setup_keyword=None),
            "skipped": dataclasses.replace(case, case_result=Skipped("not today"), case_body=[]),
        },
        stats_table={"all": {"pass": 1, "fail": 0}},
        parent_suite=Suite("parent", [], {}, {}) if depth == 1 else None,
        all_spans=(Span(0.0, 1.0), Span(1.0, 2.0)),
        tagged_pairs={"pair": (1, [Tag("x"), None])},
        last_event=Stopped("stopped", 2.5),
        last_details=Tag("details", "x") if depth % 2 else {"some": "details"},
        free_payload={"free": [1, {"form": True}]},
    )


def test_nested_model_round_trip_through_json() -> None:
    suite = _suite(3)
    assert _same(from_json(as_json(suite), Suite), suite)


def test_nested_model_round_trip_through_dicts() -> None:
    suite = _suite(3)
    assert _same(from_dict(as_dict(suite), Suite), suite)


def test_nested_model_reads_in_strict_mode() -> None:
    suite = _suite(3)
    assert _same(from_json(as_json(suite), Suite, strict=True), suite)


def test_nested_model_writes_camel_case_at_every_level() -> None:
    data = json.loads(as_json(_suite(1)))
    message = data["subSuites"][0]["suiteCases"]["failed"]["setupKeyword"]["childKeywords"][0]["logMessages"][1]
    assert message == {"messageText": "<b>bold</b>", "logLevel": "warn", "isHtml": True}


def test_wrong_value_deep_in_the_nested_model_names_its_path() -> None:
    data = json.loads(as_json(_suite(1)))
    keyword = data["subSuites"][0]["suiteCases"]["failed"]["setupKeyword"]
    keyword["childKeywords"][0]["logMessages"][0]["messageText"] = 5

    with pytest.raises(NamedTypeError) as error:
        from_dict(data, Suite)

    assert error.value.name == "sub_suites.suite_cases.failed.setup_keyword.child_keywords.log_messages.message_text"
    assert error.value.message == "Value '5' must be of type `<class 'str'>` but is `int`."


# --- random nested types from Hypothesis --------------------------------------
#
# A value fits only one type of a union: its classes have required keys of their own or a literal, and its other
# types differ in their kind of JSON, or tell apart by their elements.

_LISTS: list[Any] = [list, List, Sequence]
_DICTS: list[Any] = [dict, Dict, Mapping]
_OPTIONAL: Any = Optional
_UNION: Any = Union
_TUPLE: Any = tuple
_NAMED_TUPLE: Any = NamedTuple

_LEAVES: list[Any] = [
    int,
    str,
    bool,
    float,
    Literal["l1", "l2"],
    Status,
    Level,
    Priority,
    list[int] | list[str],
    Union[Tuple[int, str], Tuple[str, int]],
    dict[str, int] | dict[str, str],
    dict[Level, int],
    Union[Started, Stopped],
    Union[Started, dict[str, int]],
]
_USEFUL_ERRORS = ("must be of type", "matches more than one of the types", "Can't initialize")

# JSON has no NaN and no Infinity, and only a list and a dict read back as themselves for an abstract type.
st.register_type_strategy(float, st.floats(allow_nan=False, allow_infinity=False))
st.register_type_strategy(Sequence, lambda t: st.from_type(_LISTS[0][t.__args__[0]]))
st.register_type_strategy(Mapping, lambda t: st.from_type(_DICTS[0][t.__args__]))


def _class_of(key: str, fields: list[tuple[Any, bool]], camel: bool) -> Any:
    spec: list[Any] = [(key, int)]
    for index, (target, optional) in enumerate(sorted(fields, key=lambda item: item[1])):
        name = f"field_{index}_name"
        spec.append((name, target | None, field(default=None)) if optional else (name, target))
    return dataclasses.make_dataclass(f"Class_{key}", spec, bases=(CamelSnakeMixin,) if camel else ())


def _union_of(scalar: Any, first: Any, second: Any, element: Any, spelled_with_typing: bool) -> Any:
    branches = (scalar, first, second) if element is None else (scalar, first, second, _LISTS[0][element])
    return _UNION[branches] if spelled_with_typing else functools.reduce(operator.or_, branches)


def _named_tuple_of(targets: list[Any]) -> Any:
    return _NAMED_TUPLE("Named", [(f"field_{index}", target) for index, target in enumerate(targets)])


def _containers(inner: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    fields = st.lists(st.tuples(inner, st.booleans()), max_size=3)
    some = st.lists(inner, min_size=1, max_size=3)
    return st.one_of(
        st.tuples(st.sampled_from(_LISTS), inner).map(lambda item: item[0][item[1]]),
        st.tuples(st.sampled_from(_DICTS), inner).map(lambda item: item[0][str, item[1]]),
        inner.map(lambda target: _TUPLE[target, ...]),
        some.map(lambda targets: _TUPLE[tuple(targets)]),
        some.map(_named_tuple_of),
        inner.map(lambda target: _OPTIONAL[target]),
        inner.map(lambda target: target | None),
        st.builds(_class_of, st.just("key_name"), fields, st.booleans()),
        st.builds(
            _union_of,
            st.sampled_from([int, str, bool]),
            st.builds(_class_of, st.just("first_key"), fields, st.booleans()),
            st.builds(_class_of, st.just("second_key"), fields, st.booleans()),
            st.none() | inner,
            st.booleans(),
        ),
    )


_TYPES = st.recursive(st.sampled_from(_LEAVES), _containers, max_leaves=6)

# An enum compares by equality, so 10.0 would pass for the value 10 of Priority.
_JSON_VALUES = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(-9, 9)
    | st.floats(allow_nan=False, allow_infinity=False).filter(lambda number: number not in (10.0, 20.0))
    | st.text(max_size=3),
    lambda children: st.lists(children, max_size=2) | st.dictionaries(st.text(max_size=2), children, max_size=2),
    max_leaves=4,
)


def _changed(value: Any) -> st.SearchStrategy[Any]:
    """`value` with one place in it replaced by another JSON value."""
    options: list[st.SearchStrategy[Any]] = [_JSON_VALUES]
    if isinstance(value, list) and value:
        options.insert(
            0,
            st.integers(0, len(value) - 1).flatmap(
                lambda i: _changed(value[i]).map(lambda changed: [*value[:i], changed, *value[i + 1 :]])
            ),
        )
    if isinstance(value, dict) and value:
        options.insert(
            0,
            st.sampled_from(sorted(value)).flatmap(
                lambda key: _changed(value[key]).map(lambda changed: {**value, key: changed})
            ),
        )
    return st.one_of(*options)


def _without_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_without_none(item) for item in value]
    return value


_HYPOTHESIS_SETTINGS = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])


@_HYPOTHESIS_SETTINGS
@given(st.data())
def test_random_types_round_trip_through_json(data: st.DataObject) -> None:
    target = data.draw(_TYPES, label="type")
    value = data.draw(st.from_type(target), label="value")
    back = from_json(as_json(value), target)
    assert _same(back, value), f"came back as {back!r}"


@_HYPOTHESIS_SETTINGS
@given(st.data())
def test_random_types_round_trip_through_dicts(data: st.DataObject) -> None:
    target = data.draw(_TYPES, label="type")
    value = data.draw(st.from_type(target), label="value")
    holder = dataclasses.make_dataclass("Holder", [("v", target)])
    back: Any = from_dict(as_dict(holder(value)), holder)
    assert _same(back.v, value), f"came back as {back.v!r}"


@_HYPOTHESIS_SETTINGS
@given(st.data())
def test_changed_json_keeps_its_content_or_fails_with_a_useful_error(data: st.DataObject) -> None:
    target = data.draw(_TYPES, label="type")
    fitting = json.loads(as_json(data.draw(st.from_type(target), label="fitting value")))
    changed = data.draw(_changed(fitting), label="changed value")
    try:
        result = from_dict(changed, target, strict=True)
    except TypeError as e:
        message = str(e)
        assert any(text in message for text in _USEFUL_ERRORS), message
        return
    # What came through writes the same JSON, so nothing was invented. A `null` can also be a field left out.
    assert _same(_without_none(json.loads(as_json(result))), _without_none(changed)), f"became {result!r}"
