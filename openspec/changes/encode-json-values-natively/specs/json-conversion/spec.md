## MODIFIED Requirements

### Requirement: `as_json` writes dataclasses, enums, tuples and sets as JSON

`as_json` SHALL write a dataclass as an object, an enum as its value, and tuples, named tuples, sets and frozensets as arrays. For any other value that JSON cannot hold, it SHALL fail with a `TypeError`. For `NaN` and infinite floats, which JSON does not allow, it SHALL fail with a `ValueError` instead of writing them.

#### Scenario: Collections

- **WHEN** `as_json` gets `(1, 2)`, a named tuple, `{1}` or `frozenset({1})`
- **THEN** it writes a JSON array with the elements

#### Scenario: Enum

- **WHEN** `as_json` gets a member of an enum
- **THEN** it writes the value of that member

#### Scenario: Formats

- **WHEN** `as_json` gets `{"a": 1}` with `indent` or `compact`
- **THEN** it writes the object over several lines with an indent of four spaces, or without any spaces
- **AND** text outside ASCII stays as it is

#### Scenario: Value that JSON cannot hold

- **WHEN** `as_json` gets `b"x"`
- **THEN** it fails with a `TypeError` whose text is `Can't get default value for <class 'bytes'> with value b'x'`

#### Scenario: Float that JSON does not allow

- **WHEN** `as_json` gets `float("nan")`, `float("inf")` or `float("-inf")`, on its own or inside a list or a dataclass
- **THEN** it fails with a `ValueError`
- **AND** it writes nothing

## REMOVED Requirements

### Requirement: Values other than JSON scalars travel as pickles

**Reason**: The encoding of keyword arguments and return values is the value format of the Robot protocol, with the agreement on pickles, typed values and the markers `__pickled__` and `__type__`. It moves from `jsonrpcpeer.json_helpers`, a general package, to the protocol package `robot_jsonrpcremote_protocol`.

**Migration**: Client and server use the value format of the protocol package; its requirements are in the capability `protocol`. `value_to_jsonable`, `jsonable_to_value` and the pickle helpers were not exported by `jsonrpcpeer.json_helpers`.
