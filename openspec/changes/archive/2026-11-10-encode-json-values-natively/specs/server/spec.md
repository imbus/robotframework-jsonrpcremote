## ADDED Requirements

### Requirement: The server states the pickle protocol that it reads

In its answer to `initialize`, the server SHALL state the highest pickle protocol of its Python as `pickle_protocol`, unless pickles are turned off; then it SHALL state none. For each client, it SHALL send and unpickle pickles only as agreed with that client.

#### Scenario: By default

- **WHEN** a client initializes a session with the server started without a pickle option
- **THEN** the answer carries `pickle_protocol` with the highest pickle protocol of the server's Python

#### Scenario: Pickles turned off

- **WHEN** the server was started with `--no-pickles`
- **THEN** its answer to `initialize` carries no `pickle_protocol`

#### Scenario: A client that reads no pickles

- **WHEN** one client states no `pickle_protocol` and another states one
- **THEN** the server sends pickles only to the second client

### Requirement: `--no-pickles` and `ROBOT_JSONRPC_PICKLES` turn pickles off for the server

The server SHALL read pickles by default. `--no-pickles` SHALL turn them off and `--pickles` on. `ROBOT_JSONRPC_PICKLES` SHALL set the default with a text that Robot Framework converts to a boolean, ignoring case: `true`, `yes`, `on` or `1`, or `false`, `no`, `off`, `0`, `none` or the empty text. Any other value SHALL be a usage error, as for the other environment variables, and an option on the command line SHALL take precedence.

#### Scenario: Turned off from the environment

- **WHEN** the server is started with `ROBOT_JSONRPC_PICKLES=no` and without a pickle option
- **THEN** its answer to `initialize` carries no `pickle_protocol`

#### Scenario: The command line takes precedence

- **WHEN** the server is started with `ROBOT_JSONRPC_PICKLES=off` and `--pickles`
- **THEN** its answer to `initialize` carries `pickle_protocol`

#### Scenario: A value that is no truth value

- **WHEN** the server is started with `ROBOT_JSONRPC_PICKLES=maybe`
- **THEN** it ends with a usage error that names `ROBOT_JSONRPC_PICKLES` and `maybe`
- **AND** it exits with exit code 2, without a traceback

### Requirement: The library definition names classes with their module and states return types

In a library definition, the server SHALL write the type of an argument with the module and qualified name of each class in it, such as `mytypes.Point`, and a built-in or standard type by the name that Robot Framework gives it, such as `int` or `datetime`, if Robot Framework resolves that name back to the type, else also by module and qualified name. Each keyword definition SHALL carry its return type in the same way, or none if the keyword declares none or the server cannot resolve it.

#### Scenario: Argument and return types of classes

- **WHEN** a library has the keyword `paint(self, color: Color, at: list[Point] | None = None) -> Point`, whose classes come from the module `mytypes`
- **THEN** its definition gives the types `mytypes.Color` and `list[mytypes.Point] | None`
- **AND** the return type `mytypes.Point`

#### Scenario: A keyword without a return type

- **WHEN** a keyword declares no return type
- **THEN** its definition carries no return type

#### Scenario: A return type that the server cannot resolve

- **WHEN** a keyword declares the return type `"NoSuchType"`, which names no class that the server can import
- **THEN** its definition carries no return type

#### Scenario: A type that Robot Framework does not resolve by its name

- **WHEN** a keyword declares the return type `Iterable[str]` of `collections.abc`
- **THEN** its definition gives the return type `collections.abc.Iterable[str]`

#### Scenario: Standard types

- **WHEN** a keyword has the argument `when: datetime`
- **THEN** its definition gives the type `datetime`

### Requirement: Keyword values travel in the value format of the protocol

The server SHALL decode the arguments of a keyword call by the declared types of the keyword's signature and encode its return value by the declared return type, in the value format of the protocol, with the pickles agreed with the client and Robot Framework's `DotDict` as a further dict type. Arguments in a typed form SHALL become the types of the signature, dataclasses included, before the keyword runs.

#### Scenario: A dataclass argument

- **WHEN** a client calls a keyword with the argument `at: mytypes.Point` with `{"x": 1, "y": 2}`
- **THEN** the keyword gets `Point(x=1, y=2)` of `mytypes.Point`

#### Scenario: An enum given by name, as Robot Framework converts it

- **WHEN** a client calls a keyword with the argument `color: mytypes.Color` with `"red"`
- **THEN** the keyword gets the member `RED`, as a local library would

#### Scenario: A declared return value without pickles

- **WHEN** a keyword whose return type is `mytypes.Point` returns `Point(x=1, y=2)` to a client that reads no pickles
- **THEN** the result is `{"x": 1, "y": 2}`

#### Scenario: A return value without a declared type

- **WHEN** a keyword without a return type returns `Point(x=1, y=2)`, once to a client that reads no pickles and once to a client with pickles agreed
- **THEN** the first result is `{"__type__": "mytypes.Point", "x": 1, "y": 2}`
- **AND** the second result is a pickle

### Requirement: An argument that may not travel or does not fit is refused before the keyword runs

The server SHALL answer a keyword call with the code `-32602`, without running the keyword, when an argument holds a pickle that was not agreed, names a class that the server cannot import or a kind that is not built, or holds a typed form that does not fit its type. The message SHALL name the argument and be worded as Robot Framework words a failed conversion. Where Robot Framework converts an argument itself, a failed conversion SHALL be reported as for a local library.

#### Scenario: A pickle without the agreement

- **WHEN** the server was started with `--no-pickles`, and a client sends an argument with the key `__pickled__`
- **THEN** the response is a JSON-RPC error with the code `-32602` whose message names the argument and says that the server reads no pickles
- **AND** the keyword does not run
- **AND** the pickle is not unpickled

#### Scenario: A dataclass form that does not fit

- **WHEN** a client calls a keyword with the argument `at: mytypes.Point` with `{"x": 1}`, and `Point` needs the field `y`
- **THEN** the response is a JSON-RPC error with the code `-32602` whose message has the form `Argument 'at' got value ... that cannot be converted to mytypes.Point: ...` and names the field `y`
- **AND** the keyword does not run

#### Scenario: An enum given by a name that it does not have

- **WHEN** a client calls a keyword with the argument `color: mytypes.Color` with `"BLUE"`, which is no member
- **THEN** the call fails as for a local library, with the message of Robot Framework that `BLUE` cannot be converted to `Color`

### Requirement: A return value that may not travel fails the call with its reason

When a keyword returns a value that cannot travel to the client under the agreement, the server SHALL answer the call with a JSON-RPC error whose message is a `TypeError` text that names the return value, its type, and that the client reads no pickles or that `--no-pickles` turned them off.

#### Scenario: An object for a client without pickles

- **WHEN** a keyword without a return type returns an object of a class that is no dataclass, enum or named tuple, to a client that reads no pickles
- **THEN** the response is a JSON-RPC error whose message names the return value, the class and that the client reads no pickles

#### Scenario: An object from a server without pickles

- **WHEN** the server was started with `--no-pickles`, and such a keyword returns such an object to a client that reads pickles
- **THEN** the response is a JSON-RPC error whose message names the return value, the class and `--no-pickles`
