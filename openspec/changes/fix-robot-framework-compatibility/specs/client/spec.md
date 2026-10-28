# Spec Delta

## ADDED Requirements

### Requirement: Server log messages are forwarded on every supported Robot Framework version

The client SHALL write every log message that the server sends during a keyword call to Robot Framework's log of that call, with the message's level and HTML flag. This SHALL hold on every Robot Framework version from the minimum that the client's package declares.

#### Scenario: Oldest supported Robot Framework version

- **WHEN** the tests run with the oldest Robot Framework version that the client's package declares
- **AND** a remote keyword logs a message at level INFO
- **THEN** the message appears in Robot Framework's log of that keyword call at level INFO

#### Scenario: HTML message

- **WHEN** a remote keyword logs a message as HTML
- **THEN** the message appears in Robot Framework's log of that keyword call as HTML

### Requirement: Console messages from the server reach the console

When the server marks a log message for the console, the client SHALL write it to Robot Framework's log and to the console. This SHALL also hold on Robot Framework versions before 7.4.

#### Scenario: Console message on a Robot Framework version before 7.4

- **WHEN** the tests run with a Robot Framework version before 7.4
- **AND** the server sends a log message marked for the console during a keyword call
- **THEN** the message appears in Robot Framework's log of that keyword call
- **AND** the message is written to the console

### Requirement: Log messages outside a keyword call are handled like those of a local library

The client SHALL NOT drop a log message that the server sends while no keyword call is running. It SHALL hand the message to Robot Framework from the thread that runs the tests as soon as control returns there, keeping the order in which the messages arrived. Robot Framework then treats it like a message that a local library logs at the same moment.

#### Scenario: Remote library logs a warning while it is imported

- **WHEN** the remote library logs a warning while it is imported, for example in its constructor
- **THEN** the warning appears among Robot Framework's execution errors, as a warning that a local library logs during its import does

#### Scenario: Remote library logs an info message while it is imported

- **WHEN** Robot Framework's syslog is enabled
- **AND** the remote library logs an info message while it is imported
- **THEN** the message appears in the syslog, as an info message that a local library logs during its import does

#### Scenario: A keyword call starts a new session

- **WHEN** a keyword call starts a new session, for example in the next test with `rpc_scope=TEST`
- **AND** the remote library logs a message while it is imported again
- **THEN** the message appears in Robot Framework's log of that keyword call

#### Scenario: Remote library logs a warning when its session ends with its scope

- **WHEN** a session ends with its `rpc_scope`
- **AND** the remote library logs a warning while the server finalizes it
- **THEN** the warning appears among Robot Framework's execution errors, as a warning that a local library's listener logs at that moment does

#### Scenario: Messages keep their order

- **WHEN** the server sends several log messages while no keyword call is running
- **THEN** Robot Framework receives them in the order in which the server sent them
