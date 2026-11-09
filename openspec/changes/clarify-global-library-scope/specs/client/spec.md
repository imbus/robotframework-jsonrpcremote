## MODIFIED Requirements

### Requirement: A reconnect after a lost connection is logged as a warning

When connect retry is enabled, the next call after a lost connection SHALL replace the session. That re-imports the remote library. On success, the client SHALL log a warning naming the cause of the loss, the time until it reconnected, the number of attempts, and that the server-side state was reset; for a `GLOBAL` library over `tcp://` or `pipe://<name>`, that its state is kept unless the server restarted. Connection attempts that do not follow a lost connection SHALL NOT log a warning.

#### Scenario: Server restarts while the session is idle

- **WHEN** connect retry is enabled for a remote library whose scope is not `GLOBAL`
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

#### Scenario: Reconnect to a GLOBAL library on a server that the client did not start

- **WHEN** connect retry is enabled for a `tcp://` or a `pipe://<name>` URI and a remote library with the scope `GLOBAL`
- **AND** the connection is lost while the session is idle
- **AND** the next keyword call is made
- **THEN** the call returns its result
- **AND** the warning says that the library's server-side state is kept unless the server restarted, and not that it was reset

#### Scenario: Reconnect to a GLOBAL library on a server that the client started

- **WHEN** connect retry is enabled for a `stdio:` or a `pipe:<command>` URI and a remote library with the scope `GLOBAL`
- **AND** the server process exits during a keyword call
- **THEN** the next call starts a new server process, with a new instance of the library
- **AND** the warning says that the library's server-side state was reset
