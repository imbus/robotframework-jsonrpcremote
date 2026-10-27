# Spec Delta

## ADDED Requirements

### Requirement: A lost connection fails every later call until the session ends

When the connection of an established session ends without the client closing it, every following keyword call in that session SHALL fail with a `ConnectionError` whose message is "Connection to '<uri>' was lost: <cause>". This SHALL last until the session ends according to `rpc_scope`. The client SHALL NOT reconnect on its own.

#### Scenario: Server goes away while the session is idle

- **WHEN** the server goes away while no keyword is running
- **AND** the next keyword call is made
- **THEN** the call fails with `ConnectionError: Connection to '<uri>' was lost: <cause>`

#### Scenario: Further calls in the same session

- **WHEN** the connection of the session has been lost
- **AND** several further keyword calls are made in the same session
- **THEN** each of them fails with the same lost-connection error
- **AND** none of them opens a new connection

#### Scenario: Session ends according to its scope

- **WHEN** the connection of a session with `rpc_scope` `TEST` has been lost
- **AND** the test ends
- **AND** the server is reachable again when the next test makes a keyword call
- **THEN** the call starts a new session and returns its result

### Requirement: The lost-connection message names the cause

The cause in a lost-connection message SHALL be "the connection was closed by the server" when the server closed the connection cleanly. Otherwise it SHALL be the type and message of the error that ended the connection. For the `stdio` transport, the cause SHALL also name the exit code of the server process.

#### Scenario: Server closes the connection cleanly

- **WHEN** the server closes the connection cleanly
- **THEN** the cause in the message is "the connection was closed by the server"

#### Scenario: Connection ends with an error

- **WHEN** the connection ends because of an error, for example a reset connection
- **THEN** the cause in the message names the error's type and message

#### Scenario: stdio server process exits

- **WHEN** the server process spawned for a `stdio:` URI exits with exit code 3
- **THEN** the cause in the message states that the server process exited with code 3

### Requirement: A keyword running when the connection is lost fails and is not sent again

A keyword call that is running when the connection is lost SHALL fail with a `ConnectionError` whose message is "Connection to '<uri>' was lost while running keyword '<name>': <cause>". The client SHALL NOT send that call again.

#### Scenario: Server goes away during a keyword call

- **WHEN** the server goes away while a keyword call is running
- **THEN** the call fails with `ConnectionError: Connection to '<uri>' was lost while running keyword '<name>': <cause>`
- **AND** the server received the call exactly once

### Requirement: Ending a session on the client side is not a loss

When the client ends a session itself, at the end of its `rpc_scope` or when the library is torn down, it SHALL NOT treat that as a lost connection. The next call SHALL start a new session.

#### Scenario: Test with rpc_scope TEST ends

- **WHEN** a test with a session in `rpc_scope` `TEST` ends
- **AND** the next test makes a keyword call
- **THEN** the call starts a new session and returns its result instead of failing with a lost-connection error
