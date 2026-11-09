## ADDED Requirements

### Requirement: The capabilities state the pickle protocol that a side reads

`ClientCapabilities` and `ServerCapabilities` SHALL have an optional field `pickle_protocol`, the highest pickle protocol that the side reads. A side without it SHALL count as reading no pickles. Pickles SHALL be agreed when both sides state a protocol, with the lower of the two; otherwise no pickles SHALL be agreed.

#### Scenario: Both sides read pickles

- **WHEN** the client states `pickle_protocol` 5 and the server states 4
- **THEN** pickles are agreed with protocol 4

#### Scenario: One side reads no pickles

- **WHEN** the client states `pickle_protocol` 5 and the server states none
- **THEN** no pickles are agreed

### Requirement: Values that JSON holds travel as plain JSON

The protocol package SHALL encode `None`, strings, integers, finite floats and booleans, and lists and dicts with string keys whose items are such values, recursively, as plain JSON, whether or not pickles are agreed. Only values of exactly these types SHALL count. Dicts of further types that the caller names, such as Robot Framework's `DotDict`, SHALL count as dicts. Decoding SHALL give plain JSON back unchanged, and `null` SHALL always be `None`.

#### Scenario: Nested lists and dicts

- **WHEN** `[1, 2.5, {"a": [True, None, "x"]}]` is encoded, with or without pickles
- **THEN** it is the same plain JSON
- **AND** decoding it gives `[1, 2.5, {"a": [True, None, "x"]}]`

#### Scenario: A further dict type

- **WHEN** a `DotDict` with the item `a` set to `1` is encoded, with `DotDict` named as a further dict type
- **THEN** it is the plain JSON object `{"a": 1}`
- **AND** decoding it gives a plain dict

#### Scenario: None for a declared type

- **WHEN** `null` is decoded for the declared type `datetime`
- **THEN** decoding gives `None`

### Requirement: Values of a declared supported type travel in their form

The protocol package SHALL encode an instance of a dataclass, an enum or a named tuple, a value of `datetime`, `date`, `time`, `timedelta`, `Decimal`, `bytes`, `bytearray`, `UUID` or `Path`, and a tuple, set, frozenset, dict with keys other than strings, `OrderedDict` or non-finite float in the form of the protocol when its place declares its type, whether or not pickles are agreed. Decoding by the declared type SHALL build the same value back, also inside lists and dicts.

#### Scenario: A dataclass

- **WHEN** `Point(x=1, y=2)` of the dataclass `mytypes.Point` is encoded for the declared type `mytypes.Point`
- **THEN** it is `{"x": 1, "y": 2}`
- **AND** decoding it by that type gives `Point(x=1, y=2)`

#### Scenario: A named tuple and an enum

- **WHEN** `Pair(1, 2)` of a named tuple and the member `RED` of an enum whose value is `"red"` are encoded for their declared types
- **THEN** they are `[1, 2]` and `"RED"`
- **AND** decoding them by these types gives `Pair(1, 2)` and the member `RED`

#### Scenario: Built-in values without a JSON form

- **WHEN** `(1, 2)`, `{1, 2}`, `frozenset({1})`, `{1: "a"}`, an `OrderedDict` with the item `a` set to `1`, `float("nan")`, `float("inf")` and `float("-inf")` are encoded for their declared types
- **THEN** they are `[1, 2]`, an array of `1` and `2`, `[1]`, `[[1, "a"]]`, `{"a": 1}`, `"NaN"`, `"Infinity"` and `"-Infinity"`
- **AND** decoding them by these types gives the same values, of the same types

#### Scenario: Standard types

- **WHEN** a `datetime` of 2025-12-18 14:30 UTC, a `datetime` of the same time without a time zone, `date(2025, 12, 18)`, `time(14, 30)`, `timedelta(minutes=1, seconds=30.5)`, `Decimal("123.45")`, a `UUID`, `b"\x00\x01"`, `bytearray(b"\x00\x01")` and the Windows path `C:\tmp\x` are encoded for their declared types
- **THEN** they are `"2025-12-18T14:30:00+00:00"`, `"2025-12-18T14:30:00"`, `"2025-12-18"`, `"14:30:00"`, `90.5`, `"123.45"`, the UUID as a string, `"AAE="`, `"AAE="` and `"C:/tmp/x"`
- **AND** decoding them by these types gives the same values, of the same types

#### Scenario: Inside lists and dicts

- **WHEN** `[Point(x=1, y=2)]` is encoded for the declared type `list[mytypes.Point]`
- **THEN** it is `[{"x": 1, "y": 2}]`
- **AND** decoding it by that type gives `[Point(x=1, y=2)]`

#### Scenario: With pickles agreed

- **WHEN** the member `RED` of the enum `mytypes.Color` is encoded for the declared type `mytypes.Color` while pickles are agreed
- **THEN** it is `"RED"`, not a pickle

### Requirement: A value that is not of its declared type travels as without one

When a value is not of the type that its place declares, the protocol package SHALL encode it as if its place declared no type. Decoding by a declared type SHALL fail as a typed value that does not fit when the form does not fit that type.

#### Scenario: A text for a declared datetime

- **WHEN** the text `"abc"` is encoded for the declared type `datetime`
- **THEN** it is the plain JSON text `"abc"`

#### Scenario: Decoding it by the declared type

- **WHEN** `"abc"` is decoded for the declared type `datetime`
- **THEN** decoding fails with a `ValueError` whose text names `datetime`

### Requirement: With pickles, values without a declared type are pickled as a whole

When pickles are agreed, the protocol package SHALL encode a value that is not plain JSON, at a place that does not fix its type, as an object with the single key `__pickled__`, whose value is the pickle of the value in hexadecimal, written with the agreed protocol. A value with any such part SHALL be pickled as a whole. Decoding SHALL unpickle it, only at the top level of a value.

#### Scenario: A tuple

- **WHEN** `(1, 2)` is encoded without a declared type, with pickles agreed with protocol 4
- **THEN** it is an object with only the key `__pickled__`, holding a pickle of protocol 4
- **AND** decoding it gives `(1, 2)`

#### Scenario: A list that holds a tuple

- **WHEN** `[1, (2, 3)]` is encoded without a declared type, with pickles agreed
- **THEN** the whole list is one pickle

#### Scenario: Subclasses of the JSON types keep their type

- **WHEN** a member of an `IntEnum`, an `OrderedDict` and a subclass of `str` are encoded without a declared type, with pickles agreed, and decoded
- **THEN** each is a pickle
- **AND** decoding gives a value of its own type

#### Scenario: Floats that JSON does not allow

- **WHEN** `float("nan")` is encoded without a declared type, with pickles agreed
- **THEN** it is a pickle, not the text `NaN`

#### Scenario: A value that cannot be pickled

- **WHEN** a lambda is encoded with pickles agreed
- **THEN** encoding fails with an error whose text names the lambda

### Requirement: Without pickles, a typed value without a declared type names it

When no pickles are agreed and the place of a supported value does not fix its type, because no type is declared, the type is `Any`, or it is a union with more than one member other than `None`, the value SHALL name its type in the key `__type__`. A dataclass SHALL carry its fields next to that key; every other value SHALL carry its form in the key `value`. Decoding SHALL build the value by that name, also inside lists and dicts, whether or not pickles are agreed.

#### Scenario: A dataclass without a declared type

- **WHEN** `Point(x=1, y=2)` of `mytypes.Point` is encoded without a declared type and without pickles
- **THEN** it is `{"__type__": "mytypes.Point", "x": 1, "y": 2}`
- **AND** decoding it gives `Point(x=1, y=2)`

#### Scenario: Built-in and standard types without a declared type

- **WHEN** `(1, 2)` is encoded for `Any`, and a `datetime` for `int | datetime`, without pickles
- **THEN** they are `{"__type__": "tuple", "value": [1, 2]}` and `{"__type__": "datetime", "value": "..."}` with the ISO 8601 text of the datetime
- **AND** decoding them gives the tuple and the datetime

#### Scenario: A union with None declares the type

- **WHEN** `Point(x=1, y=2)` is encoded for the declared type `mytypes.Point | None`
- **THEN** it is `{"x": 1, "y": 2}`, without `__type__`

#### Scenario: Inside a list

- **WHEN** `[Point(x=1, y=2), (3, 4)]` is encoded without a declared type and without pickles
- **THEN** it is `[{"__type__": "mytypes.Point", "x": 1, "y": 2}, {"__type__": "tuple", "value": [3, 4]}]`
- **AND** decoding it gives `[Point(x=1, y=2), (3, 4)]`

### Requirement: Typed values are named as in the library definition

The name of a type in `__type__` SHALL be the name that the library definition uses for it: for a class, its module and qualified name, such as `mytypes.Point`; for the built-in and standard types, `tuple`, `set`, `frozenset`, `dict`, `OrderedDict`, `float`, `datetime`, `date`, `time`, `timedelta`, `Decimal`, `bytes`, `bytearray`, `UUID` and `Path`.

#### Scenario: A nested class

- **WHEN** an instance of the dataclass `Inner`, defined inside the class `Outer` of the module `mytypes`, is encoded without a declared type and without pickles
- **THEN** its `__type__` is `mytypes.Outer.Inner`

#### Scenario: A standard type

- **WHEN** a `Decimal` is encoded without a declared type and without pickles
- **THEN** its `__type__` is `Decimal`

### Requirement: Decoding builds only the supported kinds of values

Decoding SHALL import the class that a declared type or `__type__` names and SHALL build from typed JSON only dataclasses, enums, named tuples and the built-in and standard types of the protocol, the kinds that have a form.

#### Scenario: A name of something else

- **WHEN** `{"__type__": "os.path.join", "value": ["a", "b"]}` is decoded
- **THEN** decoding fails with a `ValueError` whose text names `os.path.join`

#### Scenario: A class that is not supported

- **WHEN** `{"__type__": "collections.defaultdict", "value": {}}` is decoded
- **THEN** decoding fails with a `ValueError`

### Requirement: The markers are unambiguous

A dict that holds the key `__pickled__` or `__type__` SHALL NOT travel as plain JSON: with pickles agreed, it SHALL be pickled; without, encoding SHALL fail as for any other value that may not travel. So an object with one of these keys on the wire SHALL always be a pickle or a typed value.

#### Scenario: A dict with the key of a typed value

- **WHEN** `{"__type__": "x"}` is encoded with pickles agreed, and decoded
- **THEN** it is a pickle
- **AND** decoding gives `{"__type__": "x"}`

#### Scenario: Without pickles

- **WHEN** `{"__pickled__": "x"}` is encoded without pickles
- **THEN** encoding fails with a `TypeError`

### Requirement: A value that may not travel fails with a TypeError

When no pickles are agreed, encoding a value that is neither plain JSON nor typed JSON SHALL fail with a `TypeError` that names the type of the value. Decoding an object with the key `__pickled__` SHALL fail with a `TypeError` and SHALL NOT unpickle it.

#### Scenario: An object of an unsupported class

- **WHEN** an object of a class that is no dataclass, enum or named tuple is encoded without pickles
- **THEN** encoding fails with a `TypeError` that names the class

#### Scenario: Other subclasses of the JSON types

- **WHEN** a value of a subclass of `str` or a `defaultdict` is encoded without a declared type and without pickles
- **THEN** encoding fails with a `TypeError` that names its type

#### Scenario: A pickle without the agreement

- **WHEN** an object with the key `__pickled__` is decoded without pickles
- **THEN** decoding fails with a `TypeError`
- **AND** the pickle is not unpickled

### Requirement: A typed value that does not fit fails with a ValueError

Decoding a typed value SHALL fail with a `ValueError` when its form does not fit its type, when its class cannot be imported, or when its name is none of the supported kinds. The text SHALL name the type and give the reason, so that client and server can word it as Robot Framework words a failed conversion.

#### Scenario: A missing field

- **WHEN** `{"x": 1}` is decoded for the declared type `mytypes.Point`, whose field `y` has no default
- **THEN** decoding fails with a `ValueError` whose text names `mytypes.Point` and the field `y`

#### Scenario: A class that is not installed

- **WHEN** `{"__type__": "notinstalled.Point", "x": 1}` is decoded and no module `notinstalled` is installed
- **THEN** decoding fails with a `ValueError` whose text names `notinstalled.Point` and that the module cannot be imported
