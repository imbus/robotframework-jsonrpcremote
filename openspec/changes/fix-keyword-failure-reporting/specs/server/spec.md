# Spec Delta

## ADDED Requirements

### Requirement: The error of a failed keyword has the message of a local keyword

When a keyword that the server runs fails, the server SHALL report it with the message that Robot Framework shows for the same failure of a local keyword.

#### Scenario: Keyword raises a ValueError

- **WHEN** a keyword raises `ValueError("bad value")`
- **THEN** the server reports the failure with the message `ValueError: bad value`

#### Scenario: Keyword fails an assertion

- **WHEN** a keyword raises `AssertionError("boom")`
- **THEN** the server reports the failure with the message `boom`

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
