# server Specification

## Purpose

Defines the behavior of the `robot-jsonrpcremote-server` runtime: hosting Robot Framework libraries for connected clients over the supported transports, and starting and stopping cleanly.

## Requirements

### Requirement: Stopping closes client connections and exits

When the server is asked to stop (SIGTERM or SIGINT), it SHALL close every client connection, and the process SHALL exit with exit code 0 within a bounded time once no keyword is running anymore. This SHALL hold on every supported Python version and whether or not clients are connected.

#### Scenario: Idle client is connected

- **WHEN** a client is connected and no keyword is running
- **AND** the server receives SIGTERM
- **THEN** the client's connection is closed by the server
- **AND** the server process exits with exit code 0 within 10 seconds, without being killed

#### Scenario: No client is connected

- **WHEN** no client is connected
- **AND** the server receives SIGTERM
- **THEN** the server process exits with exit code 0 within 10 seconds, without being killed

### Requirement: Requests that can no longer run are rejected

Requests that need the Robot runner (importing or finalizing a library, running a keyword) and that are still waiting when the stop begins, or arrive afterwards, SHALL NOT be executed. The server SHALL answer them with an error stating that the server is shutting down. None of them SHALL stay unanswered.

#### Scenario: Keyword call is waiting when the stop begins

- **WHEN** a keyword call is waiting for the runner
- **AND** the stop begins
- **THEN** the call is answered with an error stating that the server is shutting down
- **AND** the keyword is not executed

#### Scenario: Keyword call arrives after the stop began

- **WHEN** the stop has begun
- **AND** a keyword call arrives before the client's connection is closed
- **THEN** the call is answered with an error stating that the server is shutting down
- **AND** the keyword is not executed

### Requirement: The result of a running keyword is delivered

A keyword that is running when the stop begins SHALL run to completion. The server SHALL deliver its result to the client before it closes that client's connection.

#### Scenario: Server is stopped during a keyword call

- **WHEN** a keyword is running
- **AND** the server receives SIGTERM
- **THEN** the client receives the keyword's result
- **AND** the server then closes the connection and exits with exit code 0

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
