# Spec Delta

## Purpose

Defines how `jsonrpcpeer.json_helpers` converts between JSON data and typed Python objects: which targets `from_dict` accepts, how `as_dict` and `as_json` write values, how `validate_types` and `ValidateMixin` check types, and which errors invalid input gives.

## ADDED Requirements

### Requirement: `from_dict` converts JSON data to the target type

`from_dict` SHALL return the value converted to the target type and SHALL fail with a `TypeError` if the value does not fit. A tuple of types SHALL work like a union. Without a target, it SHALL return the value unchanged. `from_json` SHALL do the same for a JSON document given as `str` or `bytes`.

#### Scenario: Value of the target type

- **WHEN** `from_dict` gets `5` for `int`, `"x"` for `str` or `True` for `bool`
- **THEN** it returns the value

#### Scenario: Value of another type

- **WHEN** `from_dict` gets `"x"` for `int`
- **THEN** it fails with a `TypeError` whose text is ``Value 'x' must be of type `<class 'int'>` but is `str`.``

#### Scenario: Union

- **WHEN** `from_dict` gets `1` for `int | str`, `Union[int, str]` or `(int, str)`, or `None` for `int | None`
- **THEN** it returns the value

#### Scenario: Literal

- **WHEN** `from_dict` gets `"a"` for `Literal["a", "b"]`
- **THEN** it returns `"a"`
- **AND** it fails with a `TypeError` for `"c"`

#### Scenario: Enum

- **WHEN** `from_dict` gets the value of a member for an enum type
- **THEN** it returns that member
- **AND** it fails with a `TypeError` for a value that no member has

#### Scenario: `Any` or no target

- **WHEN** `from_dict` gets a value for `Any`, or without a target
- **THEN** it returns the value unchanged

#### Scenario: Lists and dicts

- **WHEN** `from_dict` gets `[3, 1, 1]` for `list[int]` or `{"a": 1}` for `dict[str, int]`
- **THEN** it returns an equal list or dict
- **AND** it fails with a `TypeError` for `["a"]` or `{"a": "x"}`

#### Scenario: JSON as text or bytes

- **WHEN** `from_json` gets `"[1]"` or `b"[1]"` for `list[int]`
- **THEN** it returns `[1]`

### Requirement: A boolean is not a number for `from_dict`

`from_dict` SHALL reject a boolean for `int` and for `float`, and SHALL keep a boolean for a target that allows `bool`. Without `strict`, it SHALL convert an `int` to a `float` for the target `float`.

#### Scenario: Boolean for a number

- **WHEN** `from_dict` gets `True` for `int` or `float`, or `[True]` for `list[int]`
- **THEN** it fails with a `TypeError`

#### Scenario: Boolean in a union with numbers

- **WHEN** `from_dict` gets `True` for `int | float | bool`
- **THEN** it returns `True`, not a number

#### Scenario: Number for `bool`

- **WHEN** `from_dict` gets `1` for `bool`
- **THEN** it fails with a `TypeError`

#### Scenario: Integer for `float`

- **WHEN** `from_dict` gets `5` for `float`
- **THEN** it returns the `float` `5.0`
- **AND** with `strict`, it fails with a `TypeError`

### Requirement: A JSON object only becomes a class with fields

`from_dict` SHALL convert a JSON object to a dataclass or another class with annotated fields, and SHALL keep it for a mapping type or `Any`. For any other target it SHALL fail with a `TypeError` instead of returning an empty value.

#### Scenario: Object for a number

- **WHEN** `from_dict` gets `{"q": 1}` or `{}` for `float` or `complex`
- **THEN** it fails with a `TypeError`

#### Scenario: Object for a collection that is no mapping

- **WHEN** `from_dict` gets `{"q": 1}` or `{}` for `list[int]`, `tuple[int, str]`, `Sequence[int]` or `set[int]`
- **THEN** it fails with a `TypeError`

#### Scenario: Object in a union without a fitting type

- **GIVEN** a dataclass `Point` with a required field `x`
- **WHEN** `from_dict` gets `{"q": 1}` for `float | None`, `list[int] | None` or `Point | float`
- **THEN** it fails with a `TypeError`

#### Scenario: Object for a class without fields

- **WHEN** `from_dict` gets `{"q": 1}` for `object` or for a plain class without annotated fields
- **THEN** it fails with a `TypeError`

#### Scenario: Object in a union with a fitting dataclass

- **GIVEN** a dataclass `Point` with a required field `x`
- **WHEN** `from_dict` gets `{"x": 1}` for `float | Point`
- **THEN** it returns a `Point` with `x` set to `1`

#### Scenario: Dataclass without fields

- **WHEN** `from_dict` gets `{}` for a dataclass without fields
- **THEN** it returns an instance of that dataclass

### Requirement: `from_dict` fills a class from the keys of an object

`from_dict` SHALL create the target class from the keys of a JSON object and convert each value to the type of its field. A required field without a key SHALL give a `TypeError`.

#### Scenario: Keys in any order

- **WHEN** `from_dict` gets `{"b": 2, "a": 1}` for a dataclass with the fields `a` and `b`
- **THEN** it returns an instance with `a` set to `1` and `b` set to `2`

#### Scenario: Fields with defaults

- **WHEN** an object has no key for a field with a default
- **THEN** that field has its default

#### Scenario: Nested classes

- **WHEN** a field has a dataclass as its type and the object has an object for that key
- **THEN** the field holds an instance of that dataclass

#### Scenario: Class with annotated fields that is no dataclass

- **WHEN** `from_dict` gets `{"a": 1}` for a plain class with an annotated field `a` and a matching constructor
- **THEN** it returns an instance with `a` set to `1`

#### Scenario: Required field without a key

- **WHEN** an object has no key for a required field
- **THEN** `from_dict` fails with a `TypeError`

#### Scenario: `null` for a class

- **WHEN** `from_dict` gets `None` for a dataclass
- **THEN** it fails with a `TypeError`
- **AND** for the optional form of that dataclass, it returns `None`

### Requirement: Unknown keys of an object count only in strict mode

`from_dict` SHALL ignore keys that the target class does not have. With `strict`, a class that does not have all keys of the object SHALL NOT match.

#### Scenario: Unknown key without `strict`

- **WHEN** `from_dict` gets `{"a": 1, "b": 2, "c": 3}` for a dataclass with the fields `a` and `b`
- **THEN** it returns an instance with `a` set to `1` and `b` set to `2`

#### Scenario: Unknown key with `strict`

- **WHEN** `from_dict` gets the same object for the same dataclass with `strict`
- **THEN** it fails with a `TypeError`

#### Scenario: Known keys with `strict`

- **WHEN** `from_dict` gets `{"a": 1, "b": 2}` for that dataclass with `strict`
- **THEN** it returns an instance with `a` set to `1` and `b` set to `2`

### Requirement: `from_dict` picks the class that fits an object best

For several possible classes, `from_dict` SHALL choose the one whose required fields are all present and that has the most of the object's keys. It SHALL fail with a `TypeError` if no class fits or if several fit equally well.

#### Scenario: Classes with different keys

- **WHEN** `from_dict` gets an object with the keys of only one class of a union
- **THEN** it returns an instance of that class

#### Scenario: The class with more of the keys wins

- **GIVEN** a dataclass `Two` with the required fields `a` and `b` and a dataclass `Three` with the required fields `a`, `b` and `c`
- **WHEN** `from_dict` gets `{"a": 1, "b": 2, "c": 3}` for `(Two, Three)`
- **THEN** it returns a `Three`

#### Scenario: Required fields decide

- **WHEN** `from_dict` gets `{"a": 1, "b": 2}` for `(Two, Three)`
- **THEN** it returns a `Two`

#### Scenario: Several classes fit equally well

- **GIVEN** two dataclasses `A1` and `B1`, each with a required field `x`
- **WHEN** `from_dict` gets `{"x": 1}` for `(A1, B1)`
- **THEN** it fails with a `TypeError` whose text is `Value {'x': 1} of type <class 'dict'> matches more than one of the types 'A1' | 'B1'.`

#### Scenario: No class fits

- **WHEN** `from_dict` gets an object that lacks a required field of every class of a union
- **THEN** it fails with a `TypeError`

#### Scenario: Union of a simple type and classes

- **GIVEN** a dataclass `Two` as above
- **WHEN** `from_dict` gets `True` or `{"a": 1, "b": 2}` for `Union[bool, Two]`
- **THEN** it returns `True` or a `Two`

#### Scenario: Empty object for an optional class

- **WHEN** `from_dict` gets `{}` for the optional form of a dataclass whose fields all have defaults
- **THEN** it returns an instance of that dataclass, not `None`

### Requirement: A union tries its other types when an element does not fit

If an element inside a value does not fit one type of a union, `from_dict` SHALL try the other types of the union. If none fits, it SHALL fail with the error of the first type that failed.

#### Scenario: Union of list types

- **WHEN** `from_dict` gets `["a"]` for `list[int] | list[str]`
- **THEN** it returns `["a"]`

#### Scenario: Union of tuple types

- **WHEN** `from_dict` gets `["a", 1]` for `tuple[int, str] | tuple[str, int]`
- **THEN** it returns `("a", 1)`

#### Scenario: Union of dict types with classes

- **GIVEN** a dataclass `UA` with a required field `a` and a dataclass `UB` with a required field `b`
- **WHEN** `from_dict` gets `{"x": {"b": 1}}` for `dict[str, UA] | dict[str, UB]`
- **THEN** it returns a dict with a `UB` for the key `x`

#### Scenario: Wrong length goes on to the next type

- **WHEN** `from_dict` gets `[1]` for `tuple[int, str] | list[int]`
- **THEN** it returns `[1]`

#### Scenario: No type fits

- **GIVEN** a dataclass `Point` with a field `x` of type `int`
- **WHEN** `from_dict` gets `{"a": {"x": "b"}}` for `dict[str, Point] | None`
- **THEN** it fails with a `NamedTypeError` with the name `a.x`

### Requirement: Errors name the path of the wrong value

`from_dict` SHALL report a wrong value inside a class or a dict with a `NamedTypeError`, which is a `TypeError` and has the path of the value as its name.

#### Scenario: Value in a nested class

- **GIVEN** a dataclass `Point` with a field `x` of type `int`
- **WHEN** `from_dict` gets `{"a": {"x": "b"}}` for `dict[str, Point]`
- **THEN** it fails with a `NamedTypeError` with the name `a.x`
- **AND** its text starts with `Invalid value for "a.x": `

### Requirement: Abstract collection types give a list

For an abstract collection type that a list satisfies, such as `Sequence`, `MutableSequence`, `Collection` or `Iterable`, `from_dict` SHALL return a list and convert each element to the element type.

#### Scenario: Abstract collection type

- **WHEN** `from_dict` gets `[1, 2]` for `Sequence[int]`, `MutableSequence[int]`, `Collection[int]` or `Iterable[int]`, or for `Sequence` without an element type
- **THEN** it returns the list `[1, 2]`

#### Scenario: Wrong element

- **WHEN** `from_dict` gets `["a"]` for `Sequence[int]`
- **THEN** it fails with a `TypeError`

#### Scenario: Text is no collection

- **WHEN** `from_dict` gets `"abc"` for `Sequence[str]`
- **THEN** it fails with a `TypeError`

#### Scenario: Set types are not supported

- **WHEN** `from_dict` gets `[1, 2]` for `set[int]`
- **THEN** it fails with a `TypeError` whose text names `set[int]`

### Requirement: Tuple types check their length and positions

`from_dict` SHALL convert a list to a tuple type only if its length fits and each position has the type declared for it. `tuple[T, ...]` SHALL check each element against `T`, and `tuple` without arguments SHALL take any list.

#### Scenario: Fitting list

- **WHEN** `from_dict` gets `[1, "a"]` for `tuple[int, str]`
- **THEN** it returns `(1, "a")`

#### Scenario: Wrong type at a position

- **WHEN** `from_dict` gets `["a", 1]` for `tuple[int, str]`
- **THEN** it fails with a `TypeError`

#### Scenario: Wrong length

- **WHEN** `from_dict` gets `[1]` or `[1, "a", 2]` for `tuple[int, str]`
- **THEN** it fails with a `TypeError`

#### Scenario: Tuple of any length

- **WHEN** `from_dict` gets `[1, 2]` or `[]` for `tuple[int, ...]`
- **THEN** it returns `(1, 2)` or `()`
- **AND** it fails with a `TypeError` for `["a"]`

#### Scenario: Tuple without arguments

- **WHEN** `from_dict` gets `[1, "a"]` for `tuple`
- **THEN** it returns `(1, "a")`

#### Scenario: Tuple in a union

- **WHEN** `from_dict` gets `[1, 5]` for `Union[str, tuple[int, int]]`
- **THEN** it returns `(1, 5)`

### Requirement: A named tuple takes a list by position

`from_dict` SHALL convert a list to a named tuple by position and check each position against the type of its field. Fields without a value SHALL keep their defaults. A JSON object SHALL convert to a named tuple by its field names.

#### Scenario: Fitting list

- **GIVEN** a named tuple `Pair` with the fields `x` of type `int` and `y` of type `str`
- **WHEN** `from_dict` gets `[1, "a"]` for `Pair`
- **THEN** it returns `Pair(1, "a")`

#### Scenario: Wrong type at a position

- **WHEN** `from_dict` gets `["a", 1]` for `Pair`
- **THEN** it fails with a `TypeError`

#### Scenario: Named tuple with one field

- **GIVEN** a named tuple `One` with the field `x` of type `int`
- **WHEN** `from_dict` gets `[1]` for `One`
- **THEN** it returns `One(1)`

#### Scenario: Fields with defaults

- **GIVEN** a named tuple `Defaults` with the fields `x` and `y` of type `int`, both with the default `0`
- **WHEN** `from_dict` gets `[1]` for `Defaults`
- **THEN** it returns `Defaults(1, 0)`

#### Scenario: Wrong length

- **WHEN** `from_dict` gets `[1, 2, 3]` for `Defaults`, or `[1]` for `Pair`
- **THEN** it fails with a `TypeError`

#### Scenario: Written and read back

- **WHEN** `from_json` gets the result of `as_json(Pair(1, "a"))` for `Pair`
- **THEN** it returns `Pair(1, "a")`

#### Scenario: Object for a named tuple

- **WHEN** `from_dict` gets `{"x": 1, "y": "a"}` for `Pair`
- **THEN** it returns `Pair(1, "a")`

### Requirement: Dict keys are checked against the key type

`from_dict` SHALL convert each key of an object to the key type of a `dict[K, V]` or `Mapping[K, V]` and SHALL fail with a `TypeError` if a key does not fit. It SHALL NOT convert a string to a number for a key.

#### Scenario: Key of the wrong type

- **WHEN** `from_dict` gets `{"a": "b"}` for `dict[int, str]`
- **THEN** it fails with a `TypeError`

#### Scenario: Number as a string

- **WHEN** `from_dict` gets `{"1": "b"}` for `dict[int, str]`
- **THEN** it fails with a `TypeError`

#### Scenario: Key of the key type

- **WHEN** `from_dict` gets `{1: "b"}` for `dict[int, str]`
- **THEN** it returns `{1: "b"}`

#### Scenario: Enum as a key

- **WHEN** `from_dict` gets the value of an enum member as a key for a dict with that enum as its key type
- **THEN** the result has that member as its key

#### Scenario: Open key types

- **WHEN** `from_dict` gets `{"a": 1}` for `dict` or `dict[Any, Any]`
- **THEN** it returns `{"a": 1}`

### Requirement: Field names in JSON follow the alias and the case of the class

`as_dict`, `as_json` and `from_dict` SHALL use the `alias` metadata of a field as its name in JSON. A class with `CamelSnakeMixin` SHALL use camel case for its other fields in JSON.

#### Scenario: Alias

- **GIVEN** a dataclass with a field `a` that has the alias `a_test`
- **WHEN** an instance with `a` set to `2` is written with `as_json` or `as_dict`, or `{"a_test": 2}` is read with `from_dict`
- **THEN** `as_json` writes `{"a_test": 2}`, `as_dict` returns `{"a_test": 2}`, and `from_dict` returns an instance with `a` set to `2`

#### Scenario: Camel case

- **GIVEN** a dataclass with `CamelSnakeMixin` and a field `client_name`
- **WHEN** an instance is written, or an object with the key `clientName` is read
- **THEN** the key in JSON is `clientName`
- **AND** the value belongs to the field `client_name`

#### Scenario: Field names without encoding

- **WHEN** `as_dict` writes such an instance with `encode=False`
- **THEN** the keys are the names of the fields

### Requirement: `as_json` writes dataclasses, enums, tuples and sets as JSON

`as_json` SHALL write a dataclass as an object, an enum as its value, and tuples, named tuples, sets and frozensets as arrays. For any other value that JSON cannot hold, it SHALL fail with a `TypeError`.

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

### Requirement: `as_json` leaves out some fields of a dataclass

`as_json` SHALL leave out fields with the metadata `nosave`, fields with `init=False` unless they have the metadata `force_json`, and fields that are `None` and have a default.

#### Scenario: Metadata `nosave`

- **WHEN** a field has the metadata `nosave`
- **THEN** `as_json` does not write it

#### Scenario: Field with `init=False`

- **WHEN** a field has `init=False`
- **THEN** `as_json` does not write it
- **AND** with the metadata `force_json`, `as_json` writes it

#### Scenario: `None` with and without a default

- **WHEN** a field holds `None`
- **THEN** `as_json` leaves it out if it has a default
- **AND** it writes `null` if it has none

### Requirement: `as_dict` writes a dataclass as a dict of plain values

`as_dict` SHALL accept dataclass instances only. It SHALL write every field, whatever its metadata, nested dataclasses as dicts, tuples, named tuples and sets as lists, and enums as their values. A value of any other type SHALL become its `repr()`, with a warning.

#### Scenario: No dataclass

- **WHEN** `as_dict` gets `5`
- **THEN** it fails with a `TypeError` whose text is `as_dict() should be called on dataclass instances`

#### Scenario: Plain values

- **WHEN** a field holds a nested dataclass, a tuple, a named tuple, a set, a dict or an enum member
- **THEN** the result holds a dict, a list, a list, a list, a dict or the value of that member

#### Scenario: Every field

- **WHEN** a field has the metadata `nosave` or `init=False`
- **THEN** `as_dict` writes it

#### Scenario: Value of an unknown type

- **WHEN** a field holds `b"x"`
- **THEN** the result holds the text `b'x'`
- **AND** a warning names the type and the value

### Requirement: `remove_defaults` leaves out fields that have their default

With `remove_defaults`, `as_dict` SHALL leave out every field whose value equals its default, whether that comes from `default` or from `default_factory`, also in nested dataclasses.

#### Scenario: Value from `default`

- **WHEN** a field holds its `default`
- **THEN** `as_dict` leaves it out with `remove_defaults`
- **AND** it writes a field that holds another value

#### Scenario: Value from `default_factory`

- **WHEN** a field with `default_factory=list` holds `[]`
- **THEN** `as_dict` leaves it out with `remove_defaults`
- **AND** it writes that field if it holds `["x"]`

#### Scenario: Field without a default

- **WHEN** a field has no default
- **THEN** `as_dict` writes it with `remove_defaults`

#### Scenario: Nested dataclass

- **WHEN** a nested dataclass has a field that holds its default
- **THEN** `as_dict` leaves that field out of the nested dict with `remove_defaults`

### Requirement: `validate_types` treats both spellings of a union alike

`validate_types` SHALL treat `int | str` and `Union[int, str]` alike on every supported Python version, whatever was called before in the process.

#### Scenario: First call in a process

- **WHEN** the first call in a process is `validate_types(int | str, 5)`
- **THEN** it returns no errors

#### Scenario: Value outside the union

- **WHEN** `validate_types` gets `1.5` for `int | str`
- **THEN** it returns an error that names `int`, `str` and `float`

#### Scenario: Field of a dataclass

- **GIVEN** a dataclass with `ValidateMixin` and a field `n: int | None`
- **WHEN** it is created with `3` or `None`
- **THEN** it is created
- **AND** with `"x"`, it fails with a `TypeValidationError`

### Requirement: `validate_types` reports what does not fit

`validate_types` SHALL return a list of errors, which is empty if the value fits. It SHALL check the elements of lists, the keys and values of dicts, tuples by length and position, and the elements of `tuple[T, ...]`, and it SHALL NOT raise for a value that does not fit.

#### Scenario: Element of a list

- **WHEN** `validate_types` gets `["a"]` for `list[int]`
- **THEN** it returns one error that names `int` and `str`

#### Scenario: Key and value of a dict

- **WHEN** `validate_types` gets `{1: "a"}` for `dict[str, int]`
- **THEN** it returns two errors

#### Scenario: Positions of a tuple

- **WHEN** `validate_types` gets `("a", 1)` for `tuple[int, str]`
- **THEN** it returns errors
- **AND** for `(1, "a")`, it returns no errors

#### Scenario: Length of a tuple

- **WHEN** `validate_types` gets `(1,)` for `tuple[int, str]`
- **THEN** it returns an error

#### Scenario: Tuple of any length

- **WHEN** `validate_types` gets `("a",)` for `tuple[int, ...]`
- **THEN** it returns an error and does not raise
- **AND** for `(1, 2)`, it returns no errors

#### Scenario: Literal

- **WHEN** `validate_types` gets `"b"` for `Literal["a"]`
- **THEN** it returns the error `Value b is not in ('a',)`

#### Scenario: Boolean for `int`

- **WHEN** `validate_types` gets `True` for `int`
- **THEN** it returns no errors, because it checks Python objects and a `bool` is an `int`

#### Scenario: No type or `Any`

- **WHEN** `validate_types` gets a value for `None` or `Any`
- **THEN** it returns no errors

### Requirement: `ValidateMixin` converts and checks the fields of a dataclass

A dataclass with `ValidateMixin` SHALL apply the `convert` metadata of its fields, then check each field with its `validate` metadata or else against its type, and SHALL raise a `TypeValidationError` with the errors per field.

#### Scenario: Metadata `convert`

- **WHEN** a field has a `convert` function that turns its value into an `int`, and the dataclass is created with `"5"`
- **THEN** the field holds `5`

#### Scenario: Metadata `validate`

- **WHEN** a field has a `validate` function that returns errors for its value
- **THEN** creating the dataclass fails with a `TypeValidationError`
- **AND** its `errors` map the name of the field to those errors

#### Scenario: Check against the type

- **WHEN** a field without `validate` gets a value of another type
- **THEN** creating the dataclass fails with a `TypeValidationError`

#### Scenario: Text of the error

- **WHEN** a `TypeValidationError` is shown with `str()` or `repr()`
- **THEN** the text names the class and the errors

### Requirement: The case helpers convert names between snake case and camel case

`to_snake_case` and `to_camel_case` SHALL convert names, and SHALL treat `-`, `.` and spaces as separators. They SHALL keep an empty name empty.

#### Scenario: To snake case

- **WHEN** `to_snake_case` gets `clientInfo`, `a.b`, `a b` or `a-b`
- **THEN** it returns `client_info`, `a_b`, `a_b` or `a_b`

#### Scenario: To camel case

- **WHEN** `to_camel_case` gets `client_info`, `client-info`, `a.b` or `a b`
- **THEN** it returns `clientInfo`, `clientInfo`, `aB` or `aB`

#### Scenario: Empty name

- **WHEN** either helper gets an empty name
- **THEN** it returns an empty name

#### Scenario: Leading underscore

- **WHEN** a helper gets `_name`
- **THEN** `to_snake_case` returns `_name`
- **AND** `to_camel_case` returns `name`

#### Scenario: Acronym

- **WHEN** `to_snake_case` gets `HTTPServer`
- **THEN** it returns `h_t_t_p_server`, with each capital on its own

#### Scenario: Digit after a separator

- **WHEN** `to_camel_case` gets `a_1`
- **THEN** it returns `a_1`

### Requirement: Values other than JSON scalars travel as pickles

`value_to_jsonable` SHALL keep `None`, strings, numbers and booleans, and SHALL turn any other value into an object with the key `__pickled__`. `jsonable_to_value` SHALL turn such an object back and SHALL keep every other value.

#### Scenario: JSON scalars

- **WHEN** `value_to_jsonable` gets `None`, a string, a number or a boolean
- **THEN** it returns the value

#### Scenario: Value that is pickled

- **WHEN** `value_to_jsonable` gets `complex(1, 2)`, and `jsonable_to_value` gets the result
- **THEN** the result has the key `__pickled__`
- **AND** `jsonable_to_value` returns `complex(1, 2)`

#### Scenario: Object without the key

- **WHEN** `jsonable_to_value` gets `{"a": 1}`
- **THEN** it returns `{"a": 1}`
- **AND** `jsonable_dict_to_object` fails with a `ValueError` whose text is `Dictionary does not contain pickled data`

#### Scenario: Value that cannot be pickled

- **WHEN** `value_to_jsonable` gets a lambda
- **THEN** it fails with an error whose text names the lambda
