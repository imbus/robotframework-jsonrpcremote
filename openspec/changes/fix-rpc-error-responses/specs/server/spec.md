# Spec Delta

## ADDED Requirements

### Requirement: A call before the handshake is answered with NOT_INITIALIZED

The server SHALL answer a request to import a library or to run a keyword that arrives before it has received both `robot/initialize` and `robot/initialized` with a JSON-RPC error with the code `NOT_INITIALIZED` (`-32000`).

#### Scenario: Keyword call before the handshake

- **WHEN** a client sends `robot/run_keyword` before `robot/initialize`
- **THEN** the response is a JSON-RPC error with the code `-32000`

#### Scenario: Library import before the end of the handshake

- **WHEN** a client sends `robot/initialize` and then `robot/import_library` without `robot/initialized`
- **THEN** the response is a JSON-RPC error with the code `-32000`

### Requirement: A call of an unknown keyword is answered with KEYWORD_NOT_FOUND

When a client calls a keyword that the imported library does not have, the server SHALL answer with a JSON-RPC error with the code `KEYWORD_NOT_FOUND` (`-32001`) and a message that names the keyword and the library by its real name, not by its import token.

#### Scenario: Keyword does not exist

- **WHEN** a client calls the keyword `Does Not Exist` of the imported library `MyLibrary`
- **THEN** the response is a JSON-RPC error with the code `-32001` and the message `Keyword 'Does Not Exist' not found in library 'MyLibrary'.`

### Requirement: A refused library import is answered with INVALID_PARAMS

When the server refuses to import a library because it does not serve it, or because the request names no library and the server has no default library, it SHALL answer with a JSON-RPC error with the code `INVALID_PARAMS` (`-32602`) and a message that says why. It SHALL NOT log this as an error.

#### Scenario: Library that the server does not serve

- **WHEN** the server serves only `MyLibrary` and a client imports `OtherLibrary`
- **THEN** the response is a JSON-RPC error with the code `-32602` and the message `Library 'OtherLibrary' is not available.`
- **AND** the server logs no error

#### Scenario: Import without a name

- **WHEN** the server was started without libraries and a client imports a library with an empty name
- **THEN** the response is a JSON-RPC error with the code `-32602` and a message that says that the name is needed
- **AND** the server logs no error

### Requirement: A library that fails to import is reported with Robot Framework's message

When a library fails to import on the server, the server SHALL answer with a JSON-RPC error whose message is the one that Robot Framework shows for a local library, with the traceback of the library's code and the module search path, and without frames of the server's own code.

#### Scenario: Library with a missing dependency

- **WHEN** a client imports a library whose module imports a module that does not exist
- **THEN** the response is a JSON-RPC error whose message names the missing module, the line of the library that imports it and the module search path
- **AND** neither the message nor the data of the response holds a frame of the server's own code

#### Scenario: Library whose initialization fails

- **WHEN** a client imports a library whose `__init__` raises `ValueError("cannot start")`
- **THEN** the response is a JSON-RPC error whose message holds `ValueError: cannot start` and the line of the library that raises it

### Requirement: A keyword error reports only a keyword that ran and failed

The server SHALL answer a keyword call with a `RunKeywordError` only if the keyword ran and failed. It SHALL answer a call that it cannot run or complete for another reason with a JSON-RPC error whose message says why.

#### Scenario: Unknown library token

- **WHEN** a client calls a keyword with a library token that the server does not know
- **THEN** the response is a JSON-RPC error whose message names the token
- **AND** no keyword runs

#### Scenario: Server is stopping

- **WHEN** a keyword call waits for the runner when the stop begins, or arrives after it began
- **THEN** the response is a JSON-RPC error with the message `server is shutting down`

#### Scenario: Return value that cannot be transferred

- **WHEN** a keyword returns a value that cannot be transferred to the client
- **THEN** the response is a JSON-RPC error whose message says why

#### Scenario: Wrong number of arguments

- **WHEN** a client calls a keyword with the wrong number of arguments
- **THEN** the response is a `RunKeywordResult` whose `RunKeywordError` has the message of Robot Framework, as for a local keyword

### Requirement: Error responses carry a traceback only with the server's option

By default, the error responses of the server SHALL carry no traceback, and the server SHALL log the traceback of an unexpected exception. With the option `--send-tracebacks`, the error response for an unexpected exception SHALL also carry its traceback in `data`.

#### Scenario: Server without the option

- **WHEN** the server runs without `--send-tracebacks` and a client calls a keyword with an unknown library token
- **THEN** the JSON-RPC error has no data
- **AND** the server logs the traceback at ERROR level

#### Scenario: Server with the option

- **WHEN** the server runs with `--send-tracebacks` and a client calls a keyword with an unknown library token
- **THEN** the data of the JSON-RPC error holds the traceback
- **AND** the server logs the traceback at ERROR level
