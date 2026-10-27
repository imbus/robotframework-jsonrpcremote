# Spec Delta

## MODIFIED Requirements

### Requirement: A lost connection fails every later call until the session ends

When the connection of an established session ends without the client closing it and connect retry is not enabled, every following keyword call in that session SHALL fail with a `ConnectionError` whose message is "Connection to '<uri>' was lost: <cause>". This SHALL last until the session ends according to `rpc_scope`. Without connect retry, the client SHALL NOT reconnect on its own.

#### Scenario: Server goes away while the session is idle

- **WHEN** connect retry is not enabled
- **AND** the server goes away while no keyword is running
- **AND** the next keyword call is made
- **THEN** the call fails with `ConnectionError: Connection to '<uri>' was lost: <cause>`

#### Scenario: Further calls in the same session

- **WHEN** connect retry is not enabled
- **AND** the connection of the session has been lost
- **AND** several further keyword calls are made in the same session
- **THEN** each of them fails with the same lost-connection error
- **AND** none of them opens a new connection

#### Scenario: Session ends according to its scope

- **WHEN** the connection of a session with `rpc_scope` `TEST` has been lost
- **AND** the test ends
- **AND** the server is reachable again when the next test makes a keyword call
- **THEN** the call starts a new session and returns its result

## ADDED Requirements

### Requirement: Connect retry is an opt-in configured by two options

The client SHALL accept `rpc_connect_retry_timeout`, defaulting to 0 (connect retry disabled), and `rpc_connect_retry_interval`, defaulting to 1 second. Both options and `rpc_timeout` SHALL accept seconds or Robot Framework time strings, also as plain strings. The client SHALL reject invalid or negative values, and an interval of 0 while retry is enabled, at import. These options SHALL NOT be forwarded to the remote library.

#### Scenario: Options given as Robot time strings

- **WHEN** the library is imported with `rpc_connect_retry_timeout=1 minute`, `rpc_connect_retry_interval=2s` and `rpc_timeout=15s`
- **THEN** the client waits up to 60 seconds for a connection, retries every 2 seconds and limits each attempt to 15 seconds

#### Scenario: Invalid option value

- **WHEN** the library is imported with `rpc_connect_retry_timeout=soon`
- **THEN** the import fails with an error that names `rpc_connect_retry_timeout`

#### Scenario: Interval of zero while retry is enabled

- **WHEN** the library is imported with `rpc_connect_retry_timeout=10s` and `rpc_connect_retry_interval=0`
- **THEN** the import fails with an error that names `rpc_connect_retry_interval`

#### Scenario: Options are not forwarded

- **WHEN** the library is imported with the connect retry options and a named init argument for the remote library
- **THEN** the remote library receives only its own init argument

### Requirement: With connect retry every connection attempt is repeated within the window

When connect retry is enabled and a connection attempt fails, the client SHALL try again every `rpc_connect_retry_interval` until an attempt succeeds or `rpc_connect_retry_timeout` has passed. This SHALL apply at library import, when a new session starts and when a lost session is replaced. Each attempt SHALL be limited by `rpc_timeout`.

#### Scenario: Server comes up during the library import

- **WHEN** connect retry is enabled
- **AND** the server starts accepting connections a few seconds after the library import began
- **THEN** the import waits and succeeds

#### Scenario: Server is down when a new session starts

- **WHEN** connect retry is enabled
- **AND** a test with `rpc_scope` `TEST` makes its first keyword call while the server is still starting
- **THEN** the call waits until the server accepts connections and returns its result

### Requirement: Connect retry gives up once per outage

If the window passes without a successful connection, the waiting call SHALL fail with a `ConnectionError` naming the URI, the window, the number of attempts and the last error. Until a connection succeeds again, every further call SHALL make exactly one connection attempt without waiting. After a successful connection, the next outage SHALL get the full window again.

#### Scenario: Server stays down

- **WHEN** connect retry is enabled with a window of 2 seconds
- **AND** the server stays down
- **THEN** the first call fails after about 2 seconds with a `ConnectionError` naming the URI, the window, the number of attempts and the last error
- **AND** the next call fails after a single connection attempt, without waiting for the window

#### Scenario: Server comes back after the window expired

- **WHEN** connect retry gave up during an outage
- **AND** the server is reachable again
- **THEN** the next call connects and returns its result
- **AND** a later outage again gets the full window

### Requirement: A reconnect after a lost connection is logged as a warning

When connect retry is enabled, the next call after a lost connection SHALL replace the session. That re-imports the remote library. On success, the client SHALL log a warning naming the cause of the loss, the time until it reconnected, the number of attempts, and that the library's server-side state was reset. Connection attempts that do not follow a lost connection SHALL NOT log a warning.

#### Scenario: Server restarts while the session is idle

- **WHEN** connect retry is enabled
- **AND** the server restarts while the session is idle
- **AND** the next keyword call is made
- **THEN** the call returns its result
- **AND** a warning names the cause of the loss, the time until it reconnected, the number of attempts and the reset of the server-side state

#### Scenario: stdio server process exited

- **WHEN** connect retry is enabled for a `stdio:` URI
- **AND** the server process exits with exit code 3 during a keyword call
- **THEN** that keyword call fails and is not sent again
- **AND** the next call starts a new server process and returns its result
- **AND** the warning names exit code 3

### Requirement: A changed library definition after a reconnect makes the library unusable until the session ends

After reconnecting following a lost connection, the client SHALL compare the definition of the remote library with the one registered when the library was imported. If they differ, it SHALL close the new session and fail the call with a `ConnectionError` stating that the library definition changed. Every further call SHALL fail the same way, without connecting, until the session ends according to `rpc_scope`.

#### Scenario: Server comes back with the same library

- **WHEN** connect retry is enabled
- **AND** the server restarts with the same library, which it imports as a new instance with a new name
- **THEN** the next call returns its result

#### Scenario: Server comes back with a different library version

- **WHEN** connect retry is enabled
- **AND** the server restarts with a library whose definition differs from the one registered at import
- **THEN** the next call fails with a `ConnectionError` stating that the library definition changed
- **AND** further calls in the same session fail the same way without opening a connection
- **AND** after the session ended according to `rpc_scope`, the next call starts a new session
