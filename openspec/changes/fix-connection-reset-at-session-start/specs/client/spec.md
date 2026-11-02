# Spec Delta

## ADDED Requirements

### Requirement: A connection reset while a session starts fails only the call that started it

If the connection is reset while a session starts, the client SHALL raise a connection error for the call that started the session and SHALL NOT keep the session. The Robot Framework run SHALL go on as after any other failed call: later tests and teardowns run, and the output files are complete.

#### Scenario: Reset during the library import

- **WHEN** a suite imports the library
- **AND** the connection is reset before the server has answered the handshake
- **THEN** the import fails with a connection error, which Robot Framework lists as an execution error
- **AND** the tests of the suite still run
- **AND** the run ends with a complete output file

#### Scenario: Reset when a later session starts

- **WHEN** a keyword call starts a new session
- **AND** the connection is reset before the server has answered the handshake
- **THEN** the keyword fails with a connection error, which `Run Keyword And Expect Error` can expect
- **AND** the next test runs
- **AND** the next call, made after the server became reachable, connects again and returns its result

#### Scenario: Every attempt of connect retry is reset

- **WHEN** connect retry is enabled
- **AND** every attempt within the window is reset before the server has answered the handshake
- **THEN** the call fails with the error that names the window and the number of attempts
- **AND** the run goes on

#### Scenario: The error chain has an end

- **WHEN** a session fails to start because of a connection reset
- **THEN** the error has the reset as its cause
- **AND** following the causes and contexts of the error comes to an end

#### Scenario: Asyncio reports nothing

- **WHEN** a session fails to start because of a connection reset
- **THEN** asyncio reports no exception that was never retrieved
