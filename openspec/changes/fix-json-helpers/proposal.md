# Proposal

## Why

`jsonrpcpeer.json_helpers` converts between JSON and typed Python objects, and every protocol message of client and server goes through it. Its unit tests cover 77 % of the module, and the Robot suites add nothing, because the protocol only uses some of its paths. The untested parts contain bugs in public API:

- **PEP 604 unions are rejected up to Python 3.13:** `validate_types`, which `ValidateMixin` uses, checks `origin is Union`. Before Python 3.14, `get_origin(int | None)` returns `types.UnionType` instead, so `validate_types(int | str, 5)` fails with `Expected type int | str but got <class 'int'>` on 3.10 to 3.13, and a dataclass field `n: int | None` with `ValidateMixin` rejects `3`. The result even depends on cache history: in the same process, an earlier call with `Union[int, str]` hides the bug. The module's own `is_union()` handles both forms but is not used there.
- **`from_dict` is too lax or fails for some target types:** abstract collection types fail (`from_dict([1, 2], Sequence[int])` raises `TypeError: Sequence() takes no arguments`), `tuple[int, str]` does not check the positions (`['a', 1]` is accepted), `bool` is accepted for `int`, and the key type of `dict[K, V]` is ignored.
- **Smaller defects:** the `remove_defaults` option of `as_dict` does not recognize defaults from a `default_factory`, two error messages contain typos ("Cant' get default value", "matches to more then one types"), and `_as_dict_inner` and `value_to_jsonable` contain code that can never run.

Found in the project review of 2026-10-27 (items TEST-3, JSON-1, JSON-3 and JSON-4).

## What Changes

- **Tests for the whole module:**
  - `validate_types` and `ValidateMixin`, including the field metadata `convert` and `validate` and the text of `TypeValidationError`;
  - `as_dict` and `as_json` for tuples, named tuples, sets, dicts, nested dataclasses, enums, unknown types and the field metadata `nosave`, `force_json` and `alias`, with and without `remove_defaults`;
  - `from_dict` and `from_json`, including strict mode with unknown keys, the paths in `NamedTypeError` and `bytes` input;
  - the case conversion helpers with empty names, leading underscores, dots, spaces and acronyms;
  - `jsonable_dict_to_object` with and without the pickle marker.
  Tests for unions run without a pre-filled cache.
- **Fixes:** `validate_types` and `ValidateMixin` accept PEP 604 unions on every supported Python version. `from_dict` supports abstract collection types, checks tuple positions and dict key types, and no longer accepts `bool` for `int`. `remove_defaults` recognizes `default_factory`. The typos are fixed, and the unreachable code is removed.
- **BREAKING** for direct users of `from_dict`: it rejects values it accepted before, namely a tuple with a wrong type at a position, `True` or `False` for an `int`, and dict keys of the wrong type. A conforming peer's protocol messages are not affected.

Assumptions recorded for review:

- `as_dict` keeps converting values of unknown types to their `repr()` with a warning; a test documents it.
- The module-level caches stay unbounded: they are keyed by types, which do not grow with the data.

## Capabilities

### New Capabilities

- `json-conversion`: conversion between JSON data and typed Python objects in `jsonrpcpeer.json_helpers`: type validation, conversion from and to dictionaries and JSON, and the errors for invalid input.

### Modified Capabilities

_None._

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/json_helpers.py`.
- **Public API:** stricter `from_dict` (see above); otherwise unchanged.
- **Tests:** `tests/test_json_helpers.py`, aiming at full branch coverage of the module.
- **Order:** before `encode-json-values-natively`, which changes `value_to_jsonable` and relies on these tests.
