# server Specification

## Purpose

Defines the behavior of the `robot-jsonrpcremote-server` runtime: hosting Robot Framework libraries for connected clients over the supported transports, and starting and stopping cleanly.

## Requirements

### Requirement: Stopping closes client connections and exits

When the server is asked to stop (SIGTERM or SIGINT), it SHALL close every client connection, and the process SHALL exit with exit code 0 within a bounded time once no keyword is running anymore. This SHALL hold on every supported Python version and whether or not clients are connected.

#### Scenario: Idle client is connected

- **WHEN** a client is connected and no keyword is running
- **AND** the server receives SIGTERM
- **THEN** the client's connection is closed by the server
- **AND** the server process exits with exit code 0 within 10 seconds, without being killed

#### Scenario: No client is connected

- **WHEN** no client is connected
- **AND** the server receives SIGTERM
- **THEN** the server process exits with exit code 0 within 10 seconds, without being killed

### Requirement: Requests that can no longer run are rejected

Requests that need the Robot runner (importing or finalizing a library, running a keyword) and that are still waiting when the stop begins, or arrive afterwards, SHALL NOT be executed. The server SHALL answer them with an error stating that the server is shutting down. None of them SHALL stay unanswered.

#### Scenario: Keyword call is waiting when the stop begins

- **WHEN** a keyword call is waiting for the runner
- **AND** the stop begins
- **THEN** the call is answered with an error stating that the server is shutting down
- **AND** the keyword is not executed

#### Scenario: Keyword call arrives after the stop began

- **WHEN** the stop has begun
- **AND** a keyword call arrives before the client's connection is closed
- **THEN** the call is answered with an error stating that the server is shutting down
- **AND** the keyword is not executed

### Requirement: The result of a running keyword is delivered

A keyword that is running when the stop begins SHALL run to completion. The server SHALL deliver its result to the client before it closes that client's connection.

#### Scenario: Server is stopped during a keyword call

- **WHEN** a keyword is running
- **AND** the server receives SIGTERM
- **THEN** the client receives the keyword's result
- **AND** the server then closes the connection and exits with exit code 0

### Requirement: A failed start is reported as a failure

When the server cannot start, it SHALL log the reason as an error, and the process SHALL exit with a non-zero exit code as soon as the start has failed. It SHALL NOT report that it is up and running, and it SHALL NOT wait for a start timeout before it exits.

#### Scenario: TCP port is in use

- **WHEN** the server is started on a TCP address and port that another process is already listening on
- **THEN** the log contains an error that names the address that could not be bound
- **AND** the log does not state that the server is up and running
- **AND** the process exits with a non-zero exit code without waiting for a start timeout

### Requirement: stdio mode needs a stdin it can watch

In stdio mode, the server SHALL check at start that its stdin is open and can be watched for input, as a pipe or a socket can. If it cannot, the start SHALL fail as a failed start, with an error stating that stdio mode needs such a stdin. A pipe whose writing end is already closed is a valid stdin and ends the server normally.

#### Scenario: stdin is /dev/null

- **WHEN** the server is started in stdio mode with `/dev/null` as stdin
- **THEN** the start fails with an error stating that stdio mode needs a stdin that can be watched, such as a pipe
- **AND** the process exits with a non-zero exit code instead of waiting for input

#### Scenario: stdin is a regular file

- **WHEN** the server is started in stdio mode with a regular file as stdin
- **THEN** the start fails with the same error
- **AND** the process exits with a non-zero exit code

#### Scenario: stdin is a pipe that is already closed

- **WHEN** the server is started in stdio mode with a pipe on stdin whose writing end is already closed
- **THEN** the server starts, sees the end of its input and exits with exit code 0

### Requirement: The server works with every supported Robot Framework version

The server SHALL start, import libraries and run their keywords with every Robot Framework version from the minimum that its package declares.

#### Scenario: Oldest supported Robot Framework version

- **WHEN** the server runs with the oldest Robot Framework version that its package declares
- **AND** a client imports a library whose keywords have arguments with and without default values
- **THEN** the server starts and the import succeeds
- **AND** the library definition marks exactly the arguments that have a default value as having one
- **AND** the client can run the library's keywords

### Requirement: The error of a failed keyword has the message of a local keyword

When a keyword that the server runs fails, the server SHALL report it with the message that Robot Framework shows for the same failure of a local keyword. It SHALL send the whole message, however long: what a report shows is up to the Robot Framework run that called the keyword.

#### Scenario: Keyword raises a ValueError

- **WHEN** a keyword raises `ValueError("bad value")`
- **THEN** the server reports the failure with the message `ValueError: bad value`

#### Scenario: Keyword fails an assertion

- **WHEN** a keyword raises `AssertionError("boom")`
- **THEN** the server reports the failure with the message `boom`

#### Scenario: Keyword fails with a long message

- **WHEN** a keyword fails with a message of 100 lines
- **THEN** the server reports the failure with all 100 lines

### Requirement: The error of a failed keyword names its type and carries its traceback

When a keyword that the server runs fails, the server SHALL report the name of the exception's type and its traceback, which shows the frames of the library code.

#### Scenario: Type and traceback of a failure

- **WHEN** a keyword raises `ValueError("bad value")`
- **THEN** the server reports the type `ValueError`
- **AND** a traceback that contains the line of the library that raised the error

### Requirement: The error of a failed keyword carries its failure mode

When a keyword that the server runs skips the test, fails continuably or fails fatally, as Robot Framework decides it for a local keyword, the server SHALL report the failure mode `SKIP`, `CONTINUABLE` or `FATAL`. Any other failure SHALL carry no failure mode.

#### Scenario: Skip

- **WHEN** a keyword raises `SkipExecution`
- **THEN** the server reports the failure mode `SKIP`

#### Scenario: Continuable failure

- **WHEN** a keyword raises `ContinuableFailure`
- **THEN** the server reports the failure mode `CONTINUABLE`

#### Scenario: Fatal failure

- **WHEN** a keyword raises `FatalError`
- **THEN** the server reports the failure mode `FATAL`

#### Scenario: Normal failure

- **WHEN** a keyword raises `ValueError`
- **THEN** the server reports no failure mode

### Requirement: A fatal failure of a keyword does not stop the server

A fatal failure of a keyword SHALL end only that keyword call. The server SHALL keep running and SHALL run the keywords of later calls, from the same client and from others.

#### Scenario: Keyword call after a fatal failure

- **WHEN** a keyword fails fatally
- **AND** a client then calls a keyword of the server
- **THEN** the server runs that keyword and returns its result

### Requirement: Log messages are forwarded from the client's log level on

The server SHALL forward the log messages that a library logs while it runs a keyword for a client, if their level is at or above the log level that the client reported, DEBUG and TRACE included, and SHALL NOT forward messages below it. A client that has reported no log level gets the messages from INFO on.

#### Scenario: Client at DEBUG

- **WHEN** a client reported the log level `DEBUG` and a keyword logs a DEBUG and a TRACE message
- **THEN** the server forwards the DEBUG message
- **AND** it does not forward the TRACE message

#### Scenario: Client changes its log level

- **WHEN** a client reported the log level `INFO` and later reports `TRACE`
- **AND** a keyword then logs a TRACE message
- **THEN** the server forwards the TRACE message

#### Scenario: Client without a log level

- **WHEN** a client reported no log level and a keyword logs a DEBUG and an INFO message
- **THEN** the server forwards only the INFO message

#### Scenario: Traceback of a failure

- **WHEN** a client reported the log level `DEBUG` and a keyword fails
- **THEN** the server reports the traceback in the error of the keyword call
- **AND** it does not forward the traceback as a log message

### Requirement: What the server prints does not depend on the log level of a client

The server SHALL print its log messages to stderr according to its own options, whatever log level a client reported.

#### Scenario: Library logs for a client at DEBUG

- **WHEN** a client reported the log level `DEBUG` and a library logs a DEBUG message with Python's `logging`
- **THEN** the server forwards the message to the client
- **AND** it does not print the message to stderr

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
