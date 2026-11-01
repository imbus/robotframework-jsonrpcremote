# Spec Delta

## ADDED Requirements

### Requirement: A protocol-level error fails a keyword call with its message

When the server answers a keyword call with a JSON-RPC error, the client SHALL fail the keyword call with exactly the message of the error, without its code, the name of an exception or its data, as a normal failure. The data of the error SHALL go to the log at DEBUG level under the keyword, marked with `[remote] `.

#### Scenario: Unknown keyword

- **WHEN** the server answers a keyword call with the code `-32001` and the message `Keyword 'Gone' not found in library 'MyLibrary'.`
- **THEN** the keyword call fails with the message `Keyword 'Gone' not found in library 'MyLibrary'.`
- **AND** the test does not continue after it and is not skipped

#### Scenario: Data of the error

- **WHEN** the server answers a keyword call with a JSON-RPC error with the message `boom` and the data `details`
- **THEN** the keyword call fails with the message `boom`
- **AND** the log contains `[remote] details` at DEBUG level under the failed keyword

### Requirement: A protocol-level error fails the start of a session with its message

When the server answers the library import of a new session with a JSON-RPC error, the call that started the session SHALL fail with the message of the error, without its code, the name of an exception or the client's own traceback. At a library import, the data of the error SHALL follow the message, marked with `[remote] `, as Robot Framework shows the traceback of a local library that fails to import.

#### Scenario: Refused library import

- **WHEN** the server answers the import of `JsonRpcRemote` in a suite with the message `Library 'OtherLibrary' is not available.`
- **THEN** the import fails with an error that reads `failed: Library 'OtherLibrary' is not available.` after Robot Framework's introduction
- **AND** the error holds neither `RPC Error` nor a traceback

#### Scenario: Data of the error at a library import

- **WHEN** the server answers the import of `JsonRpcRemote` in a suite with the message `boom` and the data `details`
- **THEN** the import error holds the message `boom`, followed by `[remote] details`

#### Scenario: Refused import when a later session starts

- **WHEN** `rpc_scope` is `TEST` and the server answers the import of the next test's session with the message `Library 'OtherLibrary' is not available.`
- **THEN** the keyword call that started the session fails with the message `Library 'OtherLibrary' is not available.`
