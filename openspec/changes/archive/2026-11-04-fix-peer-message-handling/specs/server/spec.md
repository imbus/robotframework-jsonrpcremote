## ADDED Requirements

### Requirement: The server leaves the console to the client

The server SHALL leave `console` out of the `robot/log` notifications for the log messages that it forwards from Robot Framework, so that the client handles them as messages of a local library.

#### Scenario: Keyword logs a warning

- **WHEN** a keyword logs a warning on the server
- **THEN** the `robot/log` notification has no `console`

#### Scenario: Keyword logs an info message

- **WHEN** a keyword logs a message at level INFO on the server
- **THEN** the `robot/log` notification has no `console`
