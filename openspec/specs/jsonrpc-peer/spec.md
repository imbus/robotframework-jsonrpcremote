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

### Requirement: An error response fails the request with an error that carries its fields

When the remote side answers a request with an error, the peer SHALL fail the request with `JsonRpcResponseError`, which has the `code`, `message` and `data` of the response and is exported by the `jsonrpcpeer` package. Its text SHALL be `RPC Error <code>: <message>`, without the data. It SHALL NOT be a connection failure.

#### Scenario: Response with code, message and data

- **WHEN** the remote side answers a request with the code `-32601`, the message `no such method` and the data `details`
- **THEN** the request fails with a `JsonRpcResponseError` with the code `-32601`, the message `no such method` and the data `details`
- **AND** its text is `RPC Error -32601: no such method`

#### Scenario: Error response is no connection failure

- **WHEN** the remote side answers a request with an error
- **THEN** the error is not an instance of `ConnectionError`
- **AND** the next request on the same connection gets its response

#### Scenario: Error is part of the package API

- **WHEN** a caller imports `JsonRpcResponseError` from the `jsonrpcpeer` package
- **THEN** the import succeeds and yields the error raised for error responses

#### Scenario: Error that is not an object

- **WHEN** the remote side answers a request with an `error` that is not an object
- **THEN** the request fails with a `JsonRpcResponseError` with the code `-32603` and the text of that value as its message

#### Scenario: Response with neither a result nor an error

- **WHEN** the remote side answers a request with a response that has neither a `result` nor an `error`
- **THEN** the request fails with a `JsonRpcResponseError` with the code `-32603`

### Requirement: A handler answers with an error of its choice by raising it

When a request handler raises `JsonRpcResponseError`, the peer SHALL answer the request with the code, message and data of that error. It SHALL NOT treat this as an unexpected exception. If an error response cannot be sent, the peer SHALL answer the request with the code `-32603` instead, so that it does not wait forever.

#### Scenario: Handler raises an error with a code

- **WHEN** a request handler raises a `JsonRpcResponseError` with the code `-32001` and the message `gone`
- **THEN** the response carries the code `-32001` and the message `gone`, without data
- **AND** the peer logs no error

#### Scenario: Handler raises an error with data

- **WHEN** a request handler raises a `JsonRpcResponseError` with the data `details`
- **THEN** the response carries the data `details`

#### Scenario: Error response that cannot be sent

- **WHEN** a request handler raises a `JsonRpcResponseError` whose data cannot be written as JSON
- **THEN** the response carries the id of the request and the code `-32603`

### Requirement: Error responses carry a traceback only if the peer is configured to send it

When the peer builds an error response from an exception, it SHALL leave out the traceback by default. The peer SHALL have an option that puts the traceback into `data` of these responses.

#### Scenario: Handler raises an unexpected exception

- **WHEN** a request handler raises `ValueError("bad value")`
- **THEN** the response carries the code `-32603` and the message `bad value`, without data

#### Scenario: Params cannot be converted

- **WHEN** the params of a request cannot be converted to the type of its handler
- **THEN** the response carries the code `-32602`, without data

#### Scenario: Message cannot be parsed

- **WHEN** a message is not valid JSON
- **THEN** the response carries the code `-32700`, without data

#### Scenario: Peer is configured to send tracebacks

- **WHEN** the peer is configured to send tracebacks
- **AND** a request handler raises `ValueError("bad value")`
- **THEN** the response carries the code `-32603` and the message `bad value`
- **AND** its data is a traceback that holds the line of the handler that raised the exception

#### Scenario: Handler's own error stays as it is

- **WHEN** the peer is configured to send tracebacks
- **AND** a request handler raises a `JsonRpcResponseError` without data
- **THEN** the response carries no data

### Requirement: The peer logs unexpected exceptions of its handlers

When a request or notification handler raises an exception other than `JsonRpcResponseError`, the peer SHALL log it at ERROR level, with the name of the method and the traceback, whether or not the response carries the traceback.

#### Scenario: Request handler raises

- **WHEN** the request handler of the method `add` raises `ValueError("bad value")`
- **THEN** the peer logs an error that names `add` and holds the traceback of the exception

#### Scenario: Notification handler raises

- **WHEN** the notification handler of the method `changed` raises `ValueError("bad value")`
- **THEN** the peer logs an error that names `changed` and holds the traceback of the exception

### Requirement: An error that ends the peer is not reported as never retrieved

If reading from the connection fails and nobody waits for the peer's completion, asyncio SHALL NOT report that error as never retrieved. A caller that waits for the completion SHALL still receive the error.

#### Scenario: Nobody waits for the completion

- **WHEN** reading from the connection fails
- **AND** nobody waits for the peer's completion
- **THEN** asyncio reports no exception that was never retrieved

#### Scenario: A caller waits for the completion afterwards

- **WHEN** reading from the connection fails
- **AND** a caller then waits for the peer's completion
- **THEN** the caller receives that error
