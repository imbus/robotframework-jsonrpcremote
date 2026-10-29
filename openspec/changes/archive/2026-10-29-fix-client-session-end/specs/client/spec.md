# Spec Delta

## ADDED Requirements

### Requirement: Ending a session does not wait for a worker that has ended

When a session is ended while its worker has already ended or ends meanwhile, ending it SHALL return as soon as the worker has ended, without waiting for `rpc_timeout`. It SHALL NOT leave behind a coroutine or task that Python reports as never awaited or as destroyed while pending.

#### Scenario: Lost session ends with its scope

- **WHEN** the connection of a session has been lost
- **AND** the session ends according to its `rpc_scope` while its worker is just finishing
- **THEN** ending it returns well within `rpc_timeout`
- **AND** Python reports no coroutine that was never awaited and no task that was destroyed while pending

#### Scenario: Worker has already ended

- **WHEN** the worker of a session has ended, but its event loop is not closed yet
- **AND** the session is ended
- **THEN** ending it returns at once
- **AND** Python reports no coroutine that was never awaited

#### Scenario: Connect retry replaces a lost session

- **WHEN** connect retry is enabled
- **AND** a keyword call finds the connection of its session lost and connects again
- **THEN** ending the lost session does not delay the call by `rpc_timeout`

### Requirement: `rpc_scope` accepts the scope names as strings

The client SHALL accept `rpc_scope` as a `SessionScope` member or as the name of one. It SHALL convert a name the way Robot Framework converts an argument to `SessionScope`, ignoring case, spaces and underscores, also when the name comes from Python code. An unknown name SHALL fail the import with an error that lists the valid names.

#### Scenario: Library built on the client passes the scope as a string

- **WHEN** Robot Framework imports a library that subclasses the client and passes `rpc_scope="TEST"`
- **THEN** each test of the suite runs in a session of its own

#### Scenario: Name in a different spelling

- **WHEN** the client is created from Python with `rpc_scope="test"`
- **THEN** its session ends with each test, as with `SessionScope.TEST`

#### Scenario: Unknown name

- **WHEN** the client is created with `rpc_scope="weekly"`, from Python or from a `.robot` file
- **THEN** the import fails with an error that lists `GLOBAL`, `SUITE` and `TEST`

## MODIFIED Requirements

### Requirement: Session errors are not printed by the worker thread

Errors that end a session's worker thread SHALL be reported to the caller that is affected by them: the call that started the session, or the keyword call that failed. They SHALL NOT be printed as an unhandled thread exception.

#### Scenario: Session fails to start

- **WHEN** a session fails to start because the server is not reachable
- **THEN** the call that started it fails with the connection error
- **AND** no unhandled exception of the session's worker thread is reported

#### Scenario: Closing the connection is cancelled from outside the session

- **WHEN** a session ends
- **AND** waiting for its connection to close is cancelled by something other than the session itself
- **THEN** the session still releases its connection and, over stdio, reaps its server process
- **AND** no unhandled exception of the session's worker thread is reported
