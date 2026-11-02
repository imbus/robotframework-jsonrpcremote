# Proposal

## Why

`jsonrpcpeer.json_helpers` converts between JSON and typed Python objects, and every protocol message of client and server goes through it. With branches counted, the unit tests reach 78 % of the module, and the Robot suites only reach the paths the protocol uses. The untested parts contain bugs in public API, and one of them corrupts values without an error:

- **A JSON object silently becomes an empty value:** `from_dict` treats nearly every class as a record, so `from_dict({"q": 1}, float)` returns `0.0`, `list[int]` returns `[]` and `tuple[int, str]` returns `()`. The protocol's `AnyType` allows one level of nesting only, so `[{"id": 1}]` arrives as `[0.0]` and `{"a": [1, 2]}` is rejected. A library that takes `[{"id": 1}]` in its import gets `[0.0]` and the test passes, also between Python peers, because import arguments travel as plain JSON. With a server in another language, this holds for every value.
- **PEP 604 unions are rejected on Python 3.12 and 3.13:** `validate_types`, which `ValidateMixin` uses, checks `origin is Union`. Before Python 3.14, `get_origin(int | None)` returns `types.UnionType` instead, so `validate_types(int | str, 5)` fails with `Expected type int | str but got <class 'int'>`, and a dataclass field `n: int | None` with `ValidateMixin` rejects `3`. The result even depends on cache history: in the same process, an earlier call with `Union[int, str]` hides the bug. The module's own `is_union()` handles both forms but is not used there.
- **`from_dict` is too lax or fails for some target types:**
  - abstract collection types fail: `from_dict([1, 2], Sequence[int])` raises `TypeError: Sequence() takes no arguments`;
  - `tuple[int, str]` checks neither positions nor length, so `['a', 1]` and `[1]` are accepted, and `tuple[int, ...]` does not check its elements;
  - a named tuple read from a list fails or gets a generator as its first field, although `as_dict` and `as_json` write named tuples as lists;
  - `bool` is accepted for `int` and becomes `1.0` for `float`;
  - the key type of `dict[K, V]` is ignored;
  - a union does not try its other types once an element does not fit one of them, so `["a"]` for `list[int] | list[str]` fails.
- **`validate_types` has the same gaps with tuples:** it does not check the positions of `tuple[int, str]`, and a wrong element of `tuple[int, ...]` raises `TypeError: isinstance() arg 2 must be a type...` instead of being reported.
- **Smaller defects:** `as_json` fails for a `frozenset`, which `as_dict` handles; the `remove_defaults` option of `as_dict` does not recognize defaults from a `default_factory`; two error messages contain typos ("Cant' get default value", "matches to more then one types"); and the module contains code that can never run, for example in `_as_dict_inner` and `value_to_jsonable`.

Found in the project review of 2026-10-27 (items TEST-3, JSON-1, JSON-3 and JSON-4), in the review of 2026-10-30 (PROTO-3), and when checking this proposal against the code on 2026-11-02. RobotCode, where this module comes from, has tests for its copy, which cover much of what is missing here.

## What Changes

- **Tests for the whole module:**
  - the tests of RobotCode's copy of this module (`tests/robotcode/core/test_dataclasses.py`), which pin how unions are matched, strict mode, aliases and empty objects; `test_really_complex_data` stays behind because it needs RobotCode's LSP types, and a smaller test with nested dataclasses takes its place;
  - `validate_types` and `ValidateMixin`, including the field metadata `convert` and `validate` and the text of `TypeValidationError`;
  - `as_dict` and `as_json` for tuples, named tuples, sets, dicts, nested dataclasses, enums, unknown types and the field metadata `nosave`, `force_json` and `alias`, with and without `remove_defaults`;
  - `from_dict` and `from_json`, including strict mode with unknown keys, the paths in `NamedTypeError`, the texts of the errors and `bytes` input;
  - the case conversion helpers with empty names, leading underscores, dots, spaces and acronyms;
  - `jsonable_dict_to_object` with and without the pickle marker, and values that cannot be pickled.

  Tests for unions run without a pre-filled cache.
- **Fixes in `from_dict`:**
  - A JSON object converts only to a dataclass or another class with annotated fields, and fails for any other target.
  - An abstract collection type that a list satisfies, such as `Sequence`, `MutableSequence`, `Collection` or `Iterable`, gives a list.
  - A tuple type checks the length and each position, `tuple[int, ...]` checks each element, and a named tuple takes a list by position.
  - `bool` is accepted neither for `int` nor for `float`; `True` in an `AnyType` stays `True`.
  - Dict keys are checked against the key type.
  - A union tries its other types when an element does not fit one of them, and fails with the first error if none fits.
- **Fixes in `validate_types`:** PEP 604 unions are accepted on every supported Python version, also by `ValidateMixin`. Tuples are checked as in `from_dict`, and a wrong element is reported instead of raising.
- **Smaller fixes:** `as_json` writes a `frozenset` as a list, `remove_defaults` recognizes `default_factory`, the typos are fixed, and the unreachable code is removed.
- **`AnyType` takes any JSON value:** it becomes `SimpleType | list[Any] | dict[str, Any]`, so nested lists and objects arrive unchanged.
- **Stricter for direct users of `from_dict`:** it rejects values it accepted before, as listed above. A conforming peer's protocol messages are not affected.

Assumptions recorded for review:

- `as_dict` keeps converting values of unknown types to their `repr()` with a warning; a test documents it.
- `as_dict` keeps writing every field: `nosave` and `init=False` only count for `as_json`; a test documents it.
- `validate_types` keeps accepting `bool` for `int`, because it checks Python objects, and there a `bool` is an `int`. `Literal` and enums keep comparing by equality, so `from_dict(True, Literal[1])` stays accepted.
- JSON object keys are strings, so `dict[int, V]` accepts only keys that already are `int`; `"1"` is not converted.
- Sets stay unsupported as targets of `from_dict`; `set[int]` fails with a clear error.
- The module-level caches stay unbounded: they are keyed by types, which do not grow with the data.

## Capabilities

### New Capabilities

- `json-conversion`: conversion between JSON data and typed Python objects in `jsonrpcpeer.json_helpers`: type validation, conversion from and to dictionaries and JSON, and the errors for invalid input.

### Modified Capabilities

- `client`: return values and argument defaults from the server may hold nested JSON, which arrives unchanged.
- `server`: arguments of a library import and of a keyword may hold nested JSON, which arrives unchanged.

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/json_helpers.py`; `AnyType` in `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py`.
- **Public API:** stricter `from_dict` (see above); otherwise unchanged.
- **Tests:** `tests/test_json_helpers.py`, with the tests taken over from RobotCode, aiming at full branch coverage of the module; `tests/test_protocol.py` for `AnyType`; a client test with `tests/fake_server.py` for a nested return value; a Robot test for a library import with a nested argument.
- **Docs:** the type conversion section of `packages/jsonrpcpeer/README.md`; the protocol page and the Protocol section of the roadmap say that JSON values may be nested.
- **Order:** before `encode-json-values-natively`, which changes `value_to_jsonable`, relies on these tests and needs nested JSON to arrive unchanged.
