# jsonrpc-peer Specification

## Purpose

Defines how the asyncio JSON-RPC 2.0 peer of the `jsonrpcpeer` package exchanges requests, responses and notifications over a stream connection, including how it behaves when that connection closes.

## Requirements

### Requirement: Connection-closed error type

The peer SHALL report a request that cannot complete because the connection is closed with `JsonRpcConnectionClosedError`. The error SHALL be exported by the `jsonrpcpeer` package and SHALL be a subclass of Python's built-in `ConnectionError`, so callers can handle it like any other connection failure.

#### Scenario: Error can be handled as a connection failure

- **WHEN** a request fails because the connection is closed
- **THEN** the caller receives a `JsonRpcConnectionClosedError`
- **AND** the error is an instance of `ConnectionError`

#### Scenario: Error is part of the package API

- **WHEN** a caller imports `JsonRpcConnectionClosedError` from the `jsonrpcpeer` package
- **THEN** the import succeeds and yields the error raised for closed connections

### Requirement: Outstanding requests fail when the connection closes

The connection counts as closed once the peer stops reading from it: the remote side closed it, reading failed, an incoming message violated the framing or size limit, or the peer was stopped. At that point the peer SHALL fail every request still waiting for a response with a connection-closed error. No request SHALL stay unresolved after the connection has closed.

#### Scenario: Remote side closes the connection

- **WHEN** a request is waiting for its response
- **AND** the remote side closes the connection
- **THEN** the request fails with a connection-closed error

#### Scenario: Peer is stopped locally

- **WHEN** a request is waiting for its response
- **AND** the peer is stopped
- **THEN** the request fails with a connection-closed error

#### Scenario: Reading from the connection fails

- **WHEN** a request is waiting for its response
- **AND** reading from the connection fails, for example because the connection was reset or a frame is malformed
- **THEN** the request fails with a connection-closed error

#### Scenario: Incoming message exceeds the size limit

- **WHEN** a request is waiting for its response
- **AND** the peer closes the connection because an incoming message exceeds its maximum message size
- **THEN** the request fails with a connection-closed error

#### Scenario: Several requests are waiting

- **WHEN** several requests are waiting for their responses
- **AND** the connection closes
- **THEN** every one of them fails with a connection-closed error

#### Scenario: Request timeout is configured

- **WHEN** the peer has a request timeout configured
- **AND** a request is waiting for its response
- **AND** the connection closes before the timeout expires
- **THEN** the request fails right away with a connection-closed error instead of waiting for the timeout

### Requirement: New requests fail after the connection closed

Once the connection has closed, the peer SHALL reject every new request immediately with a connection-closed error and SHALL NOT write it to the connection.

#### Scenario: Request sent after the connection closed

- **WHEN** the connection has closed
- **AND** a caller sends a request
- **THEN** the request fails immediately with a connection-closed error
- **AND** nothing is written to the connection

### Requirement: Cause of the closed connection is preserved

When the connection closed because reading from it raised an error, the connection-closed error of an outstanding request SHALL carry that error as its cause. In all other cases (the remote side closed it cleanly, an incoming message exceeded the size limit, or the peer was stopped) the connection-closed error SHALL have no cause.

#### Scenario: Connection closed by an error

- **WHEN** a request is waiting for its response
- **AND** reading from the connection fails with an error
- **THEN** the connection-closed error raised for the request has that error as its cause

#### Scenario: Connection closed cleanly

- **WHEN** a request is waiting for its response
- **AND** the remote side closes the connection cleanly
- **THEN** the connection-closed error raised for the request has no cause

#### Scenario: Peer is stopped

- **WHEN** a request is waiting for its response
- **AND** the peer is stopped
- **THEN** the connection-closed error raised for the request has no cause

### Requirement: Closing leaves no unreported errors behind

Failing outstanding requests SHALL NOT leave errors behind that asyncio reports as never retrieved. If the connection closes while a request is still being written and the write then fails, the caller of that request SHALL receive the connection-closed error.

#### Scenario: Connection closes while a request is being sent

- **WHEN** a caller sends a request
- **AND** the connection closes while the request is still being written
- **AND** the write then fails
- **THEN** the caller receives a connection-closed error
- **AND** asyncio reports no exception that was never retrieved

### Requirement: A peer that has ended can be garbage collected

The peer SHALL NOT keep itself alive once it has ended. When the caller no longer references a peer that has ended, the garbage collector SHALL be able to free it together with its reader, its writer and its attached endpoint.

#### Scenario: Peer is stopped

- **WHEN** a started peer is stopped
- **AND** the caller no longer references it
- **THEN** the peer is freed by a garbage collection once the event loop has finished its current step

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
- **AND** stopping returns without waiting for the writer to close

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
