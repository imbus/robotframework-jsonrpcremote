## ADDED Requirements

### Requirement: Problems that the peer reports reach Robot Framework

The client SHALL write every problem that its peer reports to Robot Framework's log as an error, which also puts it on the console and among the execution errors. The message SHALL name the URI of the server and the problem. A report SHALL NOT fail a keyword call by itself.

#### Scenario: Message without a valid length during a keyword call

- **WHEN** a keyword call is running
- **AND** the server sends a message with the header `Content-Length: abc`
- **THEN** an error that names the URI of the server and holds `abc` appears in Robot Framework's log and on the console
- **AND** the keyword call keeps waiting for its response

#### Scenario: Keyword call that gets its response after a report

- **WHEN** the server sends a message that the peer cannot read during a keyword call
- **AND** a valid response to the keyword call follows
- **THEN** the keyword passes
- **AND** the error stays among Robot Framework's execution errors

#### Scenario: Message without a valid length while the library is imported

- **WHEN** the server answers `robot/initialize` with the header `Content-Length: abc`
- **THEN** the library import fails with a timeout after `rpc_timeout`
- **AND** an error that holds `abc` appears among Robot Framework's execution errors

#### Scenario: Log message with params that cannot be converted

- **WHEN** the server sends a `robot/log` notification whose params cannot be converted
- **THEN** an error that names `robot/log` appears among Robot Framework's execution errors

#### Scenario: Error response without an id

- **WHEN** the server sends an error response with `id: null`, the code `-32700` and the message `bad`
- **THEN** an error that holds the code and the message appears among Robot Framework's execution errors

### Requirement: A log message from the server reaches the console as that of a local library

A log message that does not say whether it is for the console SHALL be handled as Robot Framework handles such a message of a local library: `WARN` and `ERROR` go to the console, other levels do not. On Robot Framework 7.4 and later, `console: false` SHALL keep a message off the console.

#### Scenario: Warning from a remote keyword

- **WHEN** a remote keyword logs a warning or an error
- **THEN** the message appears in Robot Framework's log and on the console, on every supported Robot Framework version

#### Scenario: Info message from a remote keyword

- **WHEN** a remote keyword logs a message at level INFO
- **THEN** the message appears in Robot Framework's log and not on the console

#### Scenario: Warning that is not for the console

- **WHEN** the tests run with Robot Framework 7.4 or later
- **AND** the server sends a warning with `console: false`
- **THEN** the warning appears in Robot Framework's log and not on the console
