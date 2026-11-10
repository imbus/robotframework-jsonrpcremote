## MODIFIED Requirements

### Requirement: With connect retry every connection attempt is repeated within the window

When connect retry is enabled and a connection attempt fails with a connection failure, the client SHALL try again every `rpc_connect_retry_interval` until an attempt succeeds or `rpc_connect_retry_timeout` has passed. This SHALL apply at library import, when a new session starts and when a lost session is replaced. Each attempt SHALL be limited by `rpc_timeout`.

#### Scenario: Server comes up during the library import

- **WHEN** connect retry is enabled
- **AND** the server starts accepting connections a few seconds after the library import began
- **THEN** the import waits and succeeds

#### Scenario: Server is down when a new session starts

- **WHEN** connect retry is enabled
- **AND** a test with `rpc_scope` `TEST` makes its first keyword call while the server is still starting
- **THEN** the call waits until the server accepts connections and returns its result

## ADDED Requirements

### Requirement: Connect retry repeats only connection failures

A connection failure SHALL be a failure to reach the server or to keep the connection while a session starts, such as a refused, reset or closed connection, a pipe that does not exist, or an attempt that exceeds `rpc_timeout`, and an answer of the server with the code `SHUTTING_DOWN` (`-32002`). With connect retry, every other failure of a session start SHALL fail the call at once, with the same error as without connect retry.

#### Scenario: Server does not serve the library

- **WHEN** connect retry is enabled with a window of 30 seconds
- **AND** the server answers the library import with the message `Library 'OtherLibrary' is not available.`
- **THEN** the import fails at once with the message `Library 'OtherLibrary' is not available.`
- **AND** the server receives a single library import

#### Scenario: Library fails to import on the server

- **WHEN** connect retry is enabled with a window of 30 seconds
- **AND** the library fails to import on the server because a module it needs is missing
- **THEN** the import fails at once with the error of the server, which names the missing module

#### Scenario: Server is stopping during the library import

- **WHEN** connect retry is enabled
- **AND** the server answers the first library import with the code `SHUTTING_DOWN`
- **AND** the next attempt reaches a server that imports the library
- **THEN** the import succeeds

#### Scenario: Stopping server without connect retry

- **WHEN** connect retry is disabled
- **AND** the server answers the library import with the code `SHUTTING_DOWN` and the message `server is shutting down`
- **THEN** the import fails at once with the message `server is shutting down`

#### Scenario: URI that the client cannot use

- **WHEN** connect retry is enabled with a window of 30 seconds
- **AND** the library is imported with the URI `htp://127.0.0.1:8271`
- **THEN** the import fails at once with an error that names the unsupported scheme `htp`

#### Scenario: Refused import when a lost session is replaced

- **WHEN** connect retry is enabled
- **AND** the connection of the session is lost
- **AND** the server answers the library import of the next call with the message `Library 'MyLibrary' is not available.`
- **THEN** the call fails at once with the message `Library 'MyLibrary' is not available.`
