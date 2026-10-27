# Spec Delta

## ADDED Requirements

### Requirement: A failed start is reported as a failure

When the server cannot start, it SHALL log the reason as an error, and the process SHALL exit with a non-zero exit code as soon as the start has failed. It SHALL NOT report that it is up and running, and it SHALL NOT wait for a start timeout before it exits.

#### Scenario: TCP port is in use

- **WHEN** the server is started on a TCP address and port that another process is already listening on
- **THEN** the log contains an error that names the address that could not be bound
- **AND** the log does not state that the server is up and running
- **AND** the process exits with a non-zero exit code without waiting for a start timeout

### Requirement: stdio mode needs a stdin it can watch

In stdio mode, the server SHALL check at start that its stdin is open and can be watched for input, as a pipe or a socket can. If it cannot, the start SHALL fail as a failed start, with an error stating that stdio mode needs such a stdin. A pipe whose writing end is already closed is a valid stdin and ends the server normally.

#### Scenario: stdin is /dev/null

- **WHEN** the server is started in stdio mode with `/dev/null` as stdin
- **THEN** the start fails with an error stating that stdio mode needs a stdin that can be watched, such as a pipe
- **AND** the process exits with a non-zero exit code instead of waiting for input

#### Scenario: stdin is a regular file

- **WHEN** the server is started in stdio mode with a regular file as stdin
- **THEN** the start fails with the same error
- **AND** the process exits with a non-zero exit code

#### Scenario: stdin is a pipe that is already closed

- **WHEN** the server is started in stdio mode with a pipe on stdin whose writing end is already closed
- **THEN** the server starts, sees the end of its input and exits with exit code 0
