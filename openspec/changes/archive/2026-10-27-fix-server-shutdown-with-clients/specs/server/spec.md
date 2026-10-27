# Spec Delta

## Purpose

Defines the behavior of the `robot-jsonrpcremote-server` runtime: hosting Robot Framework libraries for connected clients over the supported transports, and starting and stopping cleanly.

## ADDED Requirements

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
