# Spec Delta

## ADDED Requirements

### Requirement: A peer that has ended can be garbage collected

The peer SHALL NOT keep itself alive once it has ended. When the caller no longer references a peer that has ended, the garbage collector SHALL be able to free it together with its reader, its writer and its attached endpoint.

#### Scenario: Peer is stopped

- **WHEN** a started peer is stopped
- **AND** the caller no longer references it
- **THEN** the peer is freed by the next garbage collection

#### Scenario: Remote side closes the connection

- **WHEN** the remote side closes the connection of a started peer
- **AND** the peer's completion has resolved
- **AND** the caller no longer references the peer
- **THEN** the peer is freed by the next garbage collection

#### Scenario: Peer with an attached endpoint

- **WHEN** an endpoint is attached to a started peer
- **AND** the peer has answered a request with one of the endpoint's handlers
- **AND** the connection has closed and the caller references neither the peer nor the endpoint
- **THEN** the peer and the endpoint are freed by the next garbage collection

### Requirement: Stopping a peer whose read loop never ran ends it at once

When a peer is stopped before its read loop ran, because it was never started or because it is stopped right after it was started, stopping SHALL return at once. It SHALL end the peer as the end of its read loop does: the connection counts as closed, the peer's completion resolves as for a connection that the remote side closed cleanly, and with automatic closing enabled the writer is closed.

#### Scenario: Peer was never started

- **WHEN** a peer that was never started is stopped
- **THEN** stopping returns at once
- **AND** the peer's completion has resolved without an error

#### Scenario: Peer is stopped right after it was started

- **WHEN** a peer is started
- **AND** it is stopped before its read loop got to run
- **THEN** stopping returns at once
- **AND** the peer's completion has resolved without an error

#### Scenario: A request is waiting

- **WHEN** a request was sent on a peer that was never started and is waiting for its response
- **AND** the peer is stopped
- **THEN** the request fails with a connection-closed error that has no cause

#### Scenario: Request sent after stopping

- **WHEN** a peer that was never started has been stopped
- **AND** a caller sends a request
- **THEN** the request fails immediately with a connection-closed error
- **AND** nothing is written to the connection

#### Scenario: Automatic closing is enabled

- **WHEN** a peer with automatic closing enabled, the default, is stopped before its read loop ran
- **THEN** the peer closes its writer

#### Scenario: Automatic closing is disabled

- **WHEN** a peer with automatic closing disabled is stopped before its read loop ran
- **THEN** the peer leaves its writer open

### Requirement: A peer can be created outside a running event loop

Creating a peer SHALL NOT require a running event loop and SHALL NOT emit a warning, on every Python version that the package supports. The peer SHALL use the event loop that is running when it is first used.

#### Scenario: Peer is created without a running event loop

- **WHEN** a peer is created while no event loop is running
- **THEN** creating it succeeds without a warning
- **AND** once an event loop runs, the peer can be started and exchanges requests with a remote peer

### Requirement: Stopping a peer does not cancel the close of its writer for other callers

When the peer is stopped while it waits for its writer to close, stopping SHALL NOT cancel that close for other callers that wait for the same writer to close, and SHALL return without waiting for the close to complete.

#### Scenario: Another caller waits for the writer to close

- **WHEN** the connection of a started peer has closed and the peer waits for its writer to close
- **AND** another caller waits for the same writer to close
- **AND** the peer is stopped
- **THEN** the other caller's wait is not cancelled
- **AND** it ends normally once the writer has closed

#### Scenario: Stopping does not wait for the close

- **WHEN** the peer is stopped while it waits for its writer to close
- **THEN** stopping returns before the writer has closed

#### Scenario: The close fails after the peer was stopped

- **WHEN** the peer is stopped while it waits for its writer to close
- **AND** waiting for the close then fails, as it does for some writers such as the stdio pipe
- **THEN** asyncio reports no exception that was never retrieved
