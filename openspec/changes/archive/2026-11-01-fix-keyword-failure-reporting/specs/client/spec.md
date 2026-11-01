# Spec Delta

## ADDED Requirements

### Requirement: A failed remote keyword fails with the server's message

When a remote keyword fails, the client SHALL fail the keyword call with exactly the message that the server reports for it, without a prefix and without the protocol's error record, as Robot Framework fails a local keyword with the message of its error.

#### Scenario: Remote keyword raises a ValueError

- **WHEN** a remote keyword raises `ValueError("bad value")`
- **THEN** the keyword call fails with the message `ValueError: bad value`

#### Scenario: Remote keyword fails an assertion

- **WHEN** a remote keyword raises `AssertionError("boom")`
- **THEN** the keyword call fails with the message `boom`

### Requirement: A skipped remote keyword skips the test

When the server reports that a remote keyword skipped the test, the client SHALL skip the test with the reported message, as Robot Framework does when a local keyword skips it.

#### Scenario: Remote keyword raises SkipExecution

- **WHEN** a remote keyword raises `SkipExecution("not today")`
- **THEN** the test is skipped with the message `not today`

### Requirement: A continuable failure of a remote keyword lets the test continue

When the server reports a continuable failure of a remote keyword, the client SHALL fail the keyword call as a continuable failure, so that the test runs on and fails at its end with the reported message, as with a local keyword.

#### Scenario: Remote keyword raises ContinuableFailure

- **WHEN** a remote keyword raises `ContinuableFailure("go on")` and the test has further keywords
- **THEN** the further keywords of the test run
- **AND** the test fails with the message `go on`

### Requirement: A fatal failure of a remote keyword stops the run

When the server reports a fatal failure of a remote keyword, the client SHALL fail the keyword call as a fatal error, so that Robot Framework stops the run as it does after a fatal error of a local keyword.

#### Scenario: Remote keyword raises FatalError

- **WHEN** a remote keyword raises `FatalError("stop all")` and the suite has further tests
- **THEN** the test fails with the message `FatalError: stop all`
- **AND** the further tests are not run and fail as stopped by a fatal error

### Requirement: The traceback of a failed remote keyword is logged at DEBUG level

When the server reports the traceback of a failed remote keyword, the client SHALL write it to the log at DEBUG level, as Robot Framework logs the traceback of a failed local keyword.

#### Scenario: Traceback of a failed remote keyword

- **WHEN** a remote keyword raises an error and the server reports its traceback
- **THEN** the log contains that traceback once at DEBUG level under the failed keyword, marked as described in "Debug and trace messages from the server are marked in the log"

### Requirement: A failure that a server reports with a message only is a normal failure

The failure mode, the type and the traceback of a failed remote keyword are optional. When the server reports a failure with a message only, the client SHALL fail the keyword call with that message as a normal failure.

#### Scenario: Server reports only a message

- **WHEN** the server reports a failed remote keyword with the message `boom` and no other fields
- **THEN** the keyword call fails with the message `boom`
- **AND** the test does not continue after it and is not skipped

### Requirement: The client reports its log level to the server

When a session starts, the client SHALL tell the server the log level of the Robot Framework run. When the log level has changed since the client last reported it, for example by `Set Log Level`, the client SHALL report the new level before its next keyword call in that session.

#### Scenario: Log level at the start of a session

- **WHEN** the suite runs with `--loglevel DEBUG` and a session starts
- **THEN** the client reports the log level `DEBUG` to the server

#### Scenario: Log level changed during the run

- **WHEN** a test calls `Set Log Level    TRACE` and then a remote keyword
- **THEN** the client reports the log level `TRACE` to the server before that keyword call

### Requirement: Debug and trace messages from the server are marked in the log

The client SHALL put `[remote] ` in front of the log messages at DEBUG and TRACE level that a server sends and in front of the traceback of a failed remote keyword, so that they can be told from the client's own messages at these levels, such as Robot Framework's `Arguments` and `Return` lines. Messages at other levels SHALL appear unchanged.

#### Scenario: Debug message from the server

- **WHEN** the server sends the log message `details` at DEBUG level
- **THEN** the log contains `[remote] details` at DEBUG level

#### Scenario: Robot Framework's trace lines from both sides

- **WHEN** the suite runs at TRACE level and calls a remote keyword with the argument `value`
- **THEN** the log contains `Arguments: [ 'value' ]` from the client
- **AND** `[remote] Arguments: [ 'value' ]` from the server

#### Scenario: Info message from the server

- **WHEN** the server sends the log message `hello` at INFO level
- **THEN** the log contains `hello` at INFO level

#### Scenario: Traceback of a failed remote keyword is marked

- **WHEN** the server reports a traceback that starts with `Traceback (most recent call last):`
- **THEN** the message at DEBUG level starts with `[remote] Traceback (most recent call last):`
