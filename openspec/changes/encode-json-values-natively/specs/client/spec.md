## MODIFIED Requirements

### Requirement: Argument defaults from the server are used as they arrive

The client SHALL hand every argument default of a library definition to Robot Framework as it arrives and SHALL NOT decode a pickle in it, so that importing a library runs no code from the server on the client. A call without an argument that has a default SHALL send neither the argument nor its default.

#### Scenario: Default as text with a type that the client does not know

- **WHEN** a library definition has a keyword with the argument `button` of the type `mytypes.Button`, which the client cannot import, and the default `"LEFT"`
- **THEN** the keyword is available in Robot Framework
- **AND** Libdoc shows the argument as `button: mytypes.Button = LEFT`

#### Scenario: Default that holds a pickle

- **WHEN** a library definition has the default `{"__pickled__": "<hex>"}`, whose pickle names a module that the client does not have
- **THEN** the keyword is available in Robot Framework
- **AND** the argument has that dict as its default, unchanged

#### Scenario: Call without an argument that has a default

- **WHEN** a keyword has the arguments `f` and `g`, both with defaults
- **AND** it is called once without arguments and once with only `g=5`
- **THEN** neither call sends a value for `f` to the server

## ADDED Requirements

### Requirement: The client states the pickle protocol that it reads

In `initialize`, the client SHALL state the highest pickle protocol of its Python as `pickle_protocol`, unless pickles are turned off with `rpc_pickles`; then it SHALL state none.

#### Scenario: By default

- **WHEN** the client starts a session without `rpc_pickles`
- **THEN** its `initialize` carries `pickle_protocol` with the highest pickle protocol of its Python

#### Scenario: Pickles turned off

- **WHEN** the library is imported with `rpc_pickles=False`
- **THEN** its `initialize` carries no `pickle_protocol`

### Requirement: `rpc_pickles` turns pickles off for the client

The client SHALL accept `rpc_pickles`, defaulting to true, as a boolean or as a text that Robot Framework converts to a boolean. With a false value, the client SHALL send no pickles and SHALL unpickle none. The option SHALL NOT be forwarded to the remote library.

#### Scenario: Turned off from a suite

- **WHEN** a suite imports the library with `rpc_pickles=no`
- **THEN** the session agrees no pickles with the server

#### Scenario: The option is not forwarded

- **WHEN** the library is imported with `rpc_pickles=False` and a named init argument for the remote library
- **THEN** the remote library gets the init argument and not `rpc_pickles`

### Requirement: Keyword values travel in the value format of the protocol

The client SHALL encode the arguments of a keyword call and decode its return value in the value format of the protocol, with the pickles that the session agreed, the declared types of the keyword's arguments and its return type from the library definition, and Robot Framework's `DotDict` as a further dict type.

#### Scenario: Lists and dicts as plain JSON

- **WHEN** a keyword is called with `[1, 2]` and with a dict that `&{dict}` gives
- **THEN** the server gets `[1, 2]` and a plain JSON object, not pickles

#### Scenario: A value without a declared type and pickles agreed

- **WHEN** a keyword without type hints is called with the tuple `(1, 2)` while pickles are agreed
- **THEN** the server gets a pickle of `(1, 2)`

#### Scenario: A return value of a declared class from a server without pickles

- **WHEN** a server that reads no pickles answers a keyword whose return type is `mytypes.Point` with `{"x": 1, "y": 2}`
- **AND** `mytypes` is installed on the client
- **THEN** the keyword returns `Point(x=1, y=2)` of `mytypes.Point`

#### Scenario: A typed value without a declared type

- **WHEN** a server answers a keyword without a return type with `{"__type__": "mytypes.Point", "x": 1, "y": 2}`
- **THEN** the keyword returns `Point(x=1, y=2)`

### Requirement: The client gives Robot Framework the declared classes

The client SHALL give Robot Framework the types of a keyword's arguments with the classes that the library definition names, imported on the client, also inside lists, dicts and unions, so that Robot Framework converts arguments on the client and Libdoc shows the classes. A class that the client cannot import SHALL go to Robot Framework by the name that the definition gives.

#### Scenario: An enum that the client has installed

- **WHEN** a keyword has the argument `color` of the type `mytypes.Color`, an enum installed on the client
- **AND** a suite calls it with `red`
- **THEN** Robot Framework converts the argument on the client to the member `RED`
- **AND** the server gets `"RED"`
- **AND** the spec file of Libdoc describes the enum with its members

#### Scenario: A class that the client cannot import

- **WHEN** a keyword has the argument `at` of the type `notinstalled.Point`
- **THEN** the keyword is available in Robot Framework
- **AND** Libdoc shows the type as `notinstalled.Point`

### Requirement: A keyword value that may not travel fails the call

A keyword call SHALL fail with a `TypeError` that names the argument or the return value, its type, and that the server reads no pickles or that `rpc_pickles` turned them off: for an argument that needs a pickle, before the call is sent; for a return value that arrives as a pickle without the agreement, without unpickling it.

#### Scenario: An argument for a server without pickles

- **WHEN** a keyword without type hints is called with an object of a class that is no dataclass, enum or named tuple, and the server reads no pickles
- **THEN** the call fails with a `TypeError` that names the argument, the class and that the server reads no pickles
- **AND** nothing is sent to the server

#### Scenario: An argument with pickles turned off

- **WHEN** the library is imported with `rpc_pickles=False`, and a keyword is called with such an object
- **THEN** the call fails with a `TypeError` that names `rpc_pickles`

#### Scenario: A pickle without the agreement

- **WHEN** the library is imported with `rpc_pickles=False`, and the server answers with an object that has the key `__pickled__`
- **THEN** the call fails with a `TypeError`
- **AND** the pickle is not unpickled

### Requirement: A return value that does not fit its type fails the call

When a typed return value does not fit its type, its class is not installed on the client, or its `__type__` names none of the supported kinds, the keyword call SHALL fail with a `ValueError` worded as Robot Framework words a failed conversion, naming the return value, the type and the reason.

#### Scenario: A class that is not installed

- **WHEN** a server answers with `{"__type__": "notinstalled.Point", "x": 1}`, and no module `notinstalled` is installed on the client
- **THEN** the call fails with a `ValueError` that names the return value, `notinstalled.Point` and that the module cannot be imported

#### Scenario: A form that does not fit

- **WHEN** a server answers a keyword whose return type is `mytypes.Point` with `{"x": 1}`, and `Point` needs the field `y`
- **THEN** the call fails with a `ValueError` that names the return value, `mytypes.Point` and the field `y`
