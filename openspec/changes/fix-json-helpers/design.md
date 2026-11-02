# Design

## Context

See proposal.md for the motivation. `from_dict` works in two passes over the possible types:

1. A table maps each type to a handler for basic types, unions, literals, enums, sequences, mappings and `Any`, cached per type. The first handler that reports a match wins.
2. If no handler matched and the value is a mapping, the object path tries each type as a record: it reads the signature of the class and picks the class that fits the keys best.

The silent empty values come from the second pass. `inspect.signature(float)` only has a parameter with a default, so `float()` fits any object. `list` and `tuple` behave the same, and `set` does from Python 3.13 on, where it has a signature. `int`, `str` and `bool` escape only because they have no signature or are excluded by name.

Two facts about the protocol shape the decisions:

- `AnyType` tries `str`, `int`, `float` and `bool` in that order, so `True` is only safe today because `int` takes it first.
- Positional import arguments stay objects on the way to the library. The server turns named ones into the text `name=value` (`_endpoint.py`), and Robot Framework converts them by the type hints of `__init__`. This change does not touch that, and the library page already describes it.

The decisions below were tried out on a copy of the module before this design was written. The scenarios of the specs on Python 3.12 to 3.15, RobotCode's 102 test cases, the 314 unit tests and the 75 Robot tests all passed there, and the real server handed `[{"id": 1}]` to a library unchanged.

## Goals / Non-Goals

**Goals:**

- `from_dict` returns a value of the declared shape or raises a `TypeError`, and never invents a value.
- The structure stays: two passes, the handler table and the caches. The fixes are small changes inside it.
- Full branch coverage of the module, measured locally. CI has no coverage, as decided in `add-ci-version-matrix`.

**Non-Goals:**

- Converting between JSON types beyond the existing `int` to `float`, such as strings to numbers.
- Choosing the best type in a union of containers. The order of the union still decides among types that fit, so `1` for `float | int` stays `1.0`.
- Moving RobotCode to this module, or the module to a package of its own.
- The rest of PROTO-3: `__all__` and `__version__` of the protocol package and `from_value` for other enums.

## Decisions

### 1. A JSON object only reaches dataclasses and classes with type hints

The object path skips a class that declares no fields:

```python
type_hints = _get_type_hints_cached(origin or t)
if not type_hints and not dataclasses.is_dataclass(origin or t):
    continue
```

This one condition covers `float`, `complex`, `object`, `Decimal`, plain classes and all containers, because none of them declares fields. The dataclass check keeps classes without fields such as `ShutdownParams`, which the protocol needs for `{}`. The check for `bool` in `_get_signature_cached` can go, because `bool` no longer gets there.

Alternatives:

- Only dataclasses. That breaks annotated classes and the object form of named tuples.
- Skipping every type that has a handler. That leaves `complex`, `object`, `Decimal` and plain classes.

### 2. The basic handler looks at `bool` first

```python
if isinstance(value, bool):
    return (value, True) if t is bool else (None, False)
```

`int` and `float` have to change together. Fixing only `int` would send every `True` in an `AnyType` on to `float`, which turns it into `1.0`.

Alternative: moving `bool` to the front of `AnyType`. That protects the protocol, but not a `float | bool` of any other caller.

### 3. Tuples get their own handler, and abstract types are an explicit set

A new handler in front of the sequence handler takes everything that is a `tuple`. It reads a named tuple by position with the type hints of its fields, `tuple[T, ...]` element by element, and `tuple[A, B]` by position. A wrong length is no match, so the next type of a union gets its turn. A subclass of `tuple` without arguments keeps its type, as it did before. With `...` handled here, `Ellipsis` no longer needs to pass as a type in the handler table.

The sequence handler gives a list for `Sequence`, `MutableSequence`, `Collection` and `Iterable`, listed in one set.

Alternative: `inspect.isabstract(origin) and issubclass(list, origin)`. It is more general, but `issubclass` raises for a protocol that is not runtime-checkable, and it gives little that a caller needs.

### 4. A union remembers the first error and goes on

The loop of the first pass catches a `TypeError` from a handler, keeps the first one, and goes on with the next type. If nothing fits, including the object path, `from_dict` raises that error. A single type or an `Optional` therefore keeps today's message with its path, and a call that succeeds pays nothing.

The object path skips a union that got there this way, because all of its types have been tried. Before Python 3.14, `typing.Union` is no class that `get_type_hints` can read, so the error of that call would replace the first error.

The object path also picks a class by its keys first, as before, but among classes with equally many of the object's keys the values now decide. It creates each of them: the only one that works wins, several that work are the existing error about more than one type, and if none works, the first error comes out. So a field such as `kind: Literal["a"]` tells classes apart, which real JSON often does. Before, a tie failed at once, whatever came after it, so `(Two, TwoAgain, Three)` failed on an object with all the keys of `Three`.

A class with more of the keys and a wrong value still fails, and does not fall back to a class with fewer keys: that class would only fit by ignoring a key that has a value.

Alternatives:

- A general error that lists all types of the union. It loses the path to the wrong value.
- Handlers that report no match instead of raising. Every error would lose the message of the element.

### 5. Dict keys go through `from_dict` like values

The mapping handler converts each key to the key type. An enum as a key type works without further code. The path of an error uses `str(key)`, because a key no longer has to be a string. A `dict` without arguments and `dict[Any, Any]` take any key, and a mapping type with only a key type, such as `Counter[str]`, takes any value instead of raising an `IndexError`.

Alternative: converting `"1"` to `1` for `dict[int, V]`, as pydantic does. It needs code for each key type that nothing here uses, and the proposal rules it out.

### 6. `validate_types` uses `is_union` and checks tuples in a small helper

`is_union(origin)` replaces `origin is Union`, which also ends the dependence on cache history: both spellings of a union now take the same path. A helper checks the elements of a sequence, and for a tuple type the length and each position. Because `Ellipsis` no longer arrives as a type, the crash is gone and the end of the large `if` shrinks to one `return []`.

A list stays acceptable for a tuple type, as it is today and as it is in `from_dict`.

Alternative: rejecting a list there. The specs do not ask for it and nothing needs it.

### 7. `remove_defaults` asks the factory

A small helper compares the value with `default`, or with a fresh result of `default_factory`. A factory with a random result never matches, so such a field stays, which is correct.

Alternative: treating empty values as defaults. That is wrong for a factory that gives something other than an empty value.

### 8. `AnyType` holds `Any` in its containers

```python
AnyType: TypeAlias = SimpleType | list[Any] | dict[str, Any]
```

`from_dict` hands nested values through unchanged, which is what the receiver needs, and the protocol does not look inside them.

Alternative: a recursive alias with a `type` statement. `from_dict` would need new code for `TypeAliasType`, and the only gain is static detail that no caller uses.

### 9. The cleanup covers what cannot run and what nobody calls

- Unreachable: the second lookup and the final `raise` in `_as_dict_inner`, the repeated `None` check in `value_to_jsonable`, and two branches in the texts of `from_dict`'s errors.
- Not called by anyone, here or in RobotCode: `DefaultConfig` and `add_type_signature_to_cache`.
- `_default` checks `(set, frozenset)` instead of `typing.Set`, which only means `set`.

### 10. RobotCode's tests move into `tests/test_json_helpers.py`

They keep their names and their dataclasses, in sections of the existing file. Both projects are under the Apache License 2.0. `test_really_complex_data` stays behind, and a smaller test with nested dataclasses in camel case takes its place.

The scenario "First call in a process" runs in a subprocess, because the caches treat `int | str` and `Union[int, str]` as the same key and any earlier test could hide the bug. Clearing the caches instead would tie the test to private names.

Alternative for the large test: importing `robotcode.core.lsp.types`, which is installed here as a development tool. That ties the tests of a base package to generated types of another project.

### 11. Combinations are tested with a nested model and with Hypothesis

Full branch coverage and a mutation test that found 300 of 311 faults did not show one fault of this change: a wrong value below `Optional[...]` lost its error on Python 3.12 and 3.13, because no test had that combination. So a new file, `tests/test_json_helpers_nested.py`, goes through combinations.

- A realistic nested model is a plain test, in both directions, with `strict`, and with a wrong value deep inside.
- Hypothesis draws nested types from a recursive strategy and values for them with `from_type`. Three properties check the round trip through JSON, the round trip through dicts, and that changed JSON either keeps its content or fails with a useful error. Keeping the content needs no knowledge of the type, and it catches invented values such as `0.0` for an object.

The built-in profile `ci` of Hypothesis applies on CI by itself and uses the same examples on each run. Locally it draws new ones.

Alternative: a generator of our own with a fixed seed. It was built and compared, and found about as many faults (175 and 170 of 311 on their own), but it took about 300 lines instead of about 150, and its failures show a large random type instead of a small example such as `Optional[int]` with `{}`.

### 12. A class goes before a dict type if it knows all keys

A dict type fits any object in the first pass, so a class in the same union was never created. Now a fitting dict type waits for the object path, which only takes classes that know all keys of the object. If exactly one of them fits, it wins. Otherwise the dict comes back, also if several classes fit, because that dict loses nothing. A union with only a dict type returns at once, so the usual case pays nothing.

The `strict` check of the object path gets the same condition. It also no longer overlooks the unknown key `""`, which is falsy and passed `any(k for k in ...)`.

Alternatives:

- The first type of the union wins. A class in front would then drop unknown keys in silence.
- The behavior stays. The class of such a union is then never created, whatever the object holds.

## Risks / Trade-offs

- [`from_dict` rejects what it accepted before, such as `true` for an `int` field] → That is the purpose. All protocol messages of client and server passed on the copy, and the error of a sloppy peer now names the field.
- [Each dict key costs a conversion, and each conversion a little more bookkeeping] → Measured on Python 3.12: the four conversions of a keyword call take 18 µs as before, of about 600 µs for the whole remote keyword. A `dict[str, int]` with 1000 keys takes 0.41 ms instead of 0.20 ms, and a nested model of 124 KB 9.4 ms instead of 8.6 ms. That is small next to the network, so there is no shortcut for now.
- [Catching `TypeError` in the loop can hide a programming error in a handler while another type fits] → Handlers only raise for values that do not fit, and if nothing fits the error comes out.
- [A tie between classes creates each of them, which runs their `__post_init__`] → Only on a tie, and creating a class from data should have no side effects anyway.
- [RobotCode's copy keeps the bugs and drifts further from this one] → Accepted until RobotCode moves. Its test file stays usable there because the tests keep their names.
- [A local run can fail on an example that nobody has seen before] → That is the purpose. CI stays stable, and Hypothesis keeps the example in `.hypothesis/` and tries it first on the next run.
- [The caches take `int | float` and `float | int` as the same key, so the spelling used first in a process decides the order of the union] → Found while applying this change and not caused by it. The protocol has one spelling of each union, so it is not affected. Backlog JSON-7.
