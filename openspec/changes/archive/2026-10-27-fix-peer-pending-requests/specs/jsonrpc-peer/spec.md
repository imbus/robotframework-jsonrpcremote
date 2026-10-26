# Spec Delta

## Purpose

Defines how the asyncio JSON-RPC 2.0 peer of the `jsonrpcpeer` package exchanges requests, responses and notifications over a stream connection, including how it behaves when that connection closes.

## ADDED Requirements

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
