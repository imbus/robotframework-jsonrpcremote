# Spec Delta

## ADDED Requirements

### Requirement: Argument defaults from the server are used as they arrive

The client SHALL hand every argument default of a library definition to Robot Framework as it arrives and SHALL NOT decode a pickle in it, so that importing a library runs no code from the server on the client. A call without an argument that has a default SHALL send neither the argument nor its default.

#### Scenario: Default as text with a type that the client does not know

- **WHEN** a library definition has a keyword with the argument `button` of the type `Button`, which the client cannot import, and the default `"LEFT"`
- **THEN** the keyword is available in Robot Framework
- **AND** Libdoc shows the argument as `button: Button = LEFT`

#### Scenario: Default that holds a pickle

- **WHEN** a library definition has the default `{"__pickled__": "<hex>"}`, whose pickle names a module that the client does not have
- **THEN** the keyword is available in Robot Framework
- **AND** the argument has that dict as its default, unchanged

#### Scenario: Call without an argument that has a default

- **WHEN** a keyword has the arguments `f` and `g`, both with defaults
- **AND** it is called once without arguments and once with only `g=5`
- **THEN** neither call sends a value for `f` to the server

## MODIFIED Requirements

### Requirement: A changed library definition after a reconnect makes the library unusable until the session ends

After reconnecting following a lost connection, the client SHALL compare the definition of the remote library, including its name, with the one registered when the library was imported. If they differ, it SHALL close the new session and fail the call with a `ConnectionError` stating that the library definition changed. Every further call SHALL fail the same way, without connecting, until the session ends according to `rpc_scope`.

#### Scenario: Server comes back with the same library

- **WHEN** connect retry is enabled
- **AND** the server restarts with the same library, which it imports as a new instance
- **THEN** the next call returns its result

#### Scenario: Server comes back with a different library version

- **WHEN** connect retry is enabled
- **AND** the server restarts with a library whose definition differs from the one registered at import
- **THEN** the next call fails with a `ConnectionError` stating that the library definition changed
- **AND** further calls in the same session fail the same way without opening a connection
- **AND** after the session ended according to `rpc_scope`, the next call starts a new session

#### Scenario: Server comes back with a library of another name

- **WHEN** connect retry is enabled
- **AND** the server restarts with a library whose definition differs from the one registered at import only in its name
- **THEN** the next call fails with a `ConnectionError` stating that the library definition changed
