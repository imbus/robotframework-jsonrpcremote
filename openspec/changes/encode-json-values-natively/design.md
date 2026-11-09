# Design

## Context

See proposal.md for the motivation and the specs for the requirements; this document only explains how.

Today, keyword values cross the wire in three places, all through `value_to_jsonable` and `jsonable_to_value` of `jsonrpcpeer.json_helpers`:

- The client encodes positional and named arguments in `JsonRpcRemote.run_keyword()` (`src/JsonRpcRemote/__init__.py`) and decodes the result.
- The server decodes arguments in `_robot_run_keyword()` of `packages/server/src/robot_jsonrpcremote_server/_runner.py` and encodes the return value there, in the Robot Framework thread. A `JsonRpcResponseError` raised there, such as `KEYWORD_NOT_FOUND`, reaches the client as a JSON-RPC error. Any other exception from encoding the result becomes an error with the code `-32603`, which is what the server spec calls a return value that cannot be transferred.
- Argument defaults do not take part: the server writes them as JSON scalars or as Libdoc's text, and the client hands them over unchanged.

The two functions are not exported. The rest of `json_helpers` comes from RobotCode, and the pickle helpers are the only part that differs from it. `as_json` and `as_dict` write an enum by its value and leave `datetime` and similar types to a `default` hook, so they do not give the forms of the protocol.

Each client connection has its own `RobotServerEndpoint` on the server, which can hold what it agreed with that client. The client has one `_Session` per session, which gets the `InitializeResult` with the server's capabilities.

The library definition carries each argument type as a text, `str(arg.type)` of Robot Framework's `TypeInfo`, which names a class without its module, such as `Point`. The client hands these texts to Robot Framework in `get_keyword_types()`. Robot Framework resolves the names that it knows, such as `int`, `list[int]` or `datetime`, and leaves the others alone. Probed with Robot Framework 7.5:

- A dynamic library that gives Robot Framework the class of a dataclass gets a dict argument unchanged, without an error.
- For an enum class, `red` becomes the member `RED`, and Libdoc describes the enum with its members.
- `TypeInfo.from_string("list[mytypes.Point] | None")` parses dotted names in 7.2 and 7.5 alike, but resolves none.
- Robot Framework converts a text to `bytes` as Latin-1, so `"AAE="` becomes `b'AAE='`, and has no converter for dataclasses, `UUID` or `time`.

## Goals / Non-Goals

**Goals:**

- One implementation of the value format, used by the client, the server and the example server.
- `jsonrpcpeer` stays a general JSON-RPC package, closer to RobotCode's `dataclasses.py` than today.
- Robot Framework's own conversions keep working as for a local library: the value format converts only what Robot Framework cannot, or would convert differently.

**Non-Goals:**

- Pickles inside JSON, and signing pickles (SEC-1).
- Accepting Robot Framework's localized truth words, such as `ja`, in `ROBOT_JSONRPC_PICKLES`.
- Resolving types that a dynamic library on the server gives as texts beyond what Robot Framework itself resolves.

## Decisions

### 1. A `ValueFormat` object in the protocol package

A new module `robot_jsonrpcremote_protocol/values.py` holds a frozen dataclass `ValueFormat(pickle_protocol: int | None, dict_types: tuple[type, ...] = ())` with two methods, `encode(value, declared=...)` and `decode(data, declared=...)`. `pickle_protocol` is the agreed protocol, or `None` when no pickles are agreed. Both settings are fixed for a session, so the client keeps one object per `_Session` and the server one per endpoint, and every call passes only the value and its declared type. The module also exports the two errors and `type_name()` and `resolve_type_name()` of decision 4. The package's `__init__.py` re-exports them.

`jsonrpcpeer.json_helpers` loses `value_to_jsonable`, `jsonable_to_value`, `is_jsonable_dict`, `object_to_jsonable_dict` and `jsonable_dict_to_object`, and `as_json` passes `allow_nan=False` to `json.dumps`. Its tests move to a new `tests/test_protocol_values.py`.

*Alternatives considered:*

- Free functions with keyword arguments for the protocol and the dict types: every call site would have to pass the same two settings.
- The value format in `jsonrpcpeer`, with parameters for the Robot specifics: rejected in the proposal.

### 2. Declared types are Python type hints; the walk is our own

`declared` is a Python type hint: a class, a generic such as `list[Point]` or `dict[str, Point]`, `tuple[int, Point]` or `tuple[int, ...]`, a union, `Any`, or the marker for "not declared". The walk goes by `typing.get_origin()` and `typing.get_args()`. A place fixes the type of its value when the hint is a supported kind, a generic of supported kinds, or a union with one member besides `None`. A value that is not an instance of the declared type takes the path of an undeclared one (spec: a value that is not of its declared type travels as without one).

The supported kinds go by exact type for the built-in and standard types, and by kind for classes:
- `dataclasses.is_dataclass()`,
- a subclass of `enum.Enum`, so that a member of an `IntEnum` is an enum member here,
- a subclass of `tuple` with `_fields` for a named tuple.

`bool` is checked before `int`. Plain JSON goes by exact type, with `dict_types` counting as `dict`, and a dict that holds `__pickled__` or `__type__` never counts as plain JSON.

A dataclass is encoded from `dataclasses.fields()` with the types of `typing.get_type_hints()`, and decoded with `cls(**fields)` from the fields that take part in `__init__`. Unknown or missing keys fail, so a class that differs between the two sides shows at the call, with the field in the message. A named tuple goes by its annotations and position, and an enum member by `cls[name]`. Each field and item recurses with its own declared type, so a `datetime` field of a dataclass gets its ISO form.

*Alternative considered:* `as_dict` and `from_dict` of `jsonrpcpeer`. They write an enum by its value, leave `datetime`, `bytes` and similar types to `as_json`'s hook, and their matching of unions is made for protocol messages, not for these forms.

### 3. The forms

The forms are those of the protocol spec. The decoders are the standard ones:
- `datetime.fromisoformat()`, `date.fromisoformat()` and `time.fromisoformat()`;
- `timedelta(seconds=...)`, encoded from `total_seconds()`;
- `Decimal(text)` from `str()`;
- `base64.b64decode(text, validate=True)` from `b64encode()`;
- `UUID(text)`;
- `Path(text)` from `PurePath.as_posix()`;
- `float(text)` for `"NaN"`, `"Infinity"` and `"-Infinity"`.

A set and a frozenset become arrays in their iteration order. A dict with keys other than strings becomes an array of `[key, value]` pairs, each recursing with the declared key and value types. An `OrderedDict` with string keys becomes an object.

### 4. Type names: rendered on the server, resolved on the client

`type_name(cls)` gives the name of a type in the library definition and in `__type__`:
- for `tuple`, `set`, `frozenset`, `dict`, `OrderedDict`, `float`, `datetime`, `date`, `time`, `timedelta`, `Decimal`, `bytes`, `bytearray`, `UUID` and `Path`, the class's `__name__`, which is also Robot Framework's name for them;
- for the other built-in types and for `typing`, Robot Framework's name, as today;
- for every other class, `f"{cls.__module__}.{cls.__qualname__}"`.

`resolve_type_name(name)` reverses it:
- A name without a dot is looked up in the table of built-in and standard types.
- A dotted name is split from the right until a prefix imports with `importlib.import_module()`, and the rest is looked up as attributes. `mytypes.Outer.Inner` thus tries `mytypes.Outer`, then `mytypes`.
- The result counts only if it is a supported kind; anything else fails as a typed value that does not fit.

The server renders each argument type and the return type by walking Robot Framework's `TypeInfo`. Unions are joined with ` | `, generics written as `name[...]`, and leaves written with `type_name()` where `TypeInfo.type` is a class, else with `TypeInfo.name`. `KeywordDefinition` gets the optional field `return_type: str | None`, filled from `kw.args.return_type`. `_check_definition()` on the client compares it with the rest of the definition, without a change.

The client parses each type text with `TypeInfo.from_string()` and turns the tree into a type hint. A leaf that Robot Framework resolves keeps its type; any other leaf goes through `resolve_type_name()`. If a leaf does not resolve, the whole text stays a text: Robot Framework gets it as it is, and the value format treats the place as undeclared. The client resolves a text once per definition and keeps the result. It does so when Robot Framework first asks for the types, at the library import, so the import also imports the modules that the definition names, where they are installed.

*Alternatives considered:*

- Short names, as `str(TypeInfo)` gives them: the client could not find the class.
- Resolving only modules that are already imported: a client imports nothing of the server's types by itself, so every class of a remote library would stay unresolved.

### 5. The agreement

The client states `pickle.HIGHEST_PROTOCOL` in `ClientCapabilities.pickle_protocol` unless `rpc_pickles` is false, and the server does the same in `ServerCapabilities` unless pickles are turned off. Each side computes the agreed protocol as the lower of the two, or `None`, right after `initialize`.

- **Client:** `_Session` builds its `ValueFormat` with `dict_types=(DotDict,)`.
- **Server:** each `RobotServerEndpoint` builds its own `ValueFormat` and passes it with `run_keyword` to the runner, which encodes and decodes in the Robot Framework thread as today.

`rpc_pickles` is a parameter of `JsonRpcRemote.__init__` with the annotation `bool` and the default `True`, so Robot Framework converts `no` or `False` from a suite. Like the other `rpc_` options, it is not forwarded to the remote library.

### 6. Arguments on the client and on the server

The client takes the declared type of each value from the keyword's `ArgumentDefinition`s:
- A positional value takes the type of the positional argument at its place, and beyond these, the type of the `*args` argument.
- A named value takes the type of its argument, or of the `**kwargs` argument.

The return value is decoded by `return_type`.

The server takes the same from Robot Framework's `ArgumentSpec` of the keyword. It decodes each argument before it builds `running.Keyword`, and `_as_robot_data()` still escapes the strings that remain. When decoding fails:
- If the value was plain JSON and Robot Framework has a converter for the declared type, the server hands the plain value to Robot Framework unchanged. `TypeConverter.converter_for()` says so: it returns no converter in 7.2 and an `UnknownConverter` in 7.5 for a type without one, such as a dataclass, so both count as none. Robot Framework then converts it, as `"red"` for an enum, or fails with its own message, as for `"BLUE"`.
- Otherwise the server raises `JsonRpcResponseError(INVALID_PARAMS, ...)` with the message of decision 7, and the keyword does not run.

Robot Framework then converts what it gets once more. Decoded values are already of their type, so its converters leave them alone.

*Alternative considered:* leaving all arguments to Robot Framework. It cannot build dataclasses, `UUID` or `time`, and it reads Base64 as Latin-1.

### 7. Errors and messages

The value format raises two errors, which the module exports:

- **`ValueCannotTravelError(TypeError)`:** a value that may not travel without pickles, and a pickle that arrives without the agreement. It carries the type of the value.
- **`ValueDoesNotFitError(ValueError)`:** a typed value that does not fit, whose class cannot be imported, or whose name is not a supported kind. It carries the type name and the reason.

Client and server add the argument or the return value, and the side:

- `Argument 'at' of type 'Widget' cannot be sent: it is not JSON, and the server reads no pickles.`, or `... and rpc_pickles is off.`
- `The return value of type 'Widget' cannot be sent: it is not JSON, and the client reads no pickles.`; the server answers it with `-32603`.
- `The server sent the return value as a pickle, but the client reads no pickles.` and `Argument 'at' is a pickle, but the server reads no pickles.`; the server answers the second with `-32602`.
- `Argument 'at' got value {'x': 1} that cannot be converted to mytypes.Point: missing field 'y'.` and `Return value got value {'x': 1} that cannot be converted to mytypes.Point: missing field 'y'.`, after Robot Framework's wording. A value in these messages is shown with `repr()`, shortened as Robot Framework shortens values in its messages.

### 8. Turning pickles off on the server

`__main__.py` adds `--pickles` / `--no-pickles` with `argparse.BooleanOptionalAction`. The default comes from `ROBOT_JSONRPC_PICKLES`, read with fixed English sets: `true`, `yes`, `on` and `1`, or `false`, `no`, `off`, `0`, `none` and the empty text, ignoring case, as Robot Framework's boolean converter reads English. For `--port` and `--mode`, argparse checks a default from the environment with the `type` of the option; a flag has no `type`, so `__main__.py` reads the variable itself. Any other value ends with `parser.error()`, which gives the same usage error and exit code 2, and names the variable and the value. Without the variable, pickles are on.

### 9. The example server and the tests

- **Example server:**
  - `examples/simple-robot-jsonrpcserver` gets a module `shapes.py` with the dataclass `Point` and a keyword `Move` that takes a `Point` and two numbers and returns the moved `Point`.
  - It declares the types as `simple_robot_jsonrpcserver.shapes.Point` and states no `pickle_protocol`, as a server in another language would.
  - It uses `ValueFormat(pickle_protocol=None)` to decode and encode.
  - The client has the package installed, since it is a member of the workspace.
- **Robot suite:**
  - A new suite `atests/typed_values.robot` runs our server once with pickles and once with `--no-pickles`, on ports of its own, with a test library `TypedValuesLib.py` whose types live in `atests/typed_values_types.py`.
  - So that the client can import that module by its name, `robot.toml` gets `python-path = ["atests"]`.
  - The library has keywords with declared and undeclared arguments and return values, and one that returns the type and the value that it received.
- **Unit tests:**
  - `tests/test_protocol_values.py` covers the forms and the errors.
  - The fake server of `tests/fake_server.py` gets an attribute for its `pickle_protocol` and keeps the raw params it receives, so client tests can check what goes over the wire.

## Risks / Trade-offs

None that needs a mitigation in this change. Servers run in environments that their users trust, and the users keep the classes and their versions in step on both sides. A class that differs, or a return value that does not fit its declared type, fails the call with a message that says why.

## Migration Plan

None. Client, server, protocol package and example server change together.
