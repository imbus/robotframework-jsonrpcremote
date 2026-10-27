# client Specification

## Purpose

Defines the behavior of the `JsonRpcRemote` Robot Framework library: how it starts, uses and ends sessions with a remote server and how it reports failures to Robot Framework.

## Requirements

### Requirement: Keyword failures affect only their own call

When a keyword call fails, the client SHALL report the failure for that call only. This covers a remote keyword that raises, a server that answers the request with a JSON-RPC error, and a request that cannot complete. Later calls in the same session SHALL NOT re-raise that failure.

#### Scenario: Remote keyword raises

- **WHEN** a remote keyword raises an error
- **THEN** the call fails with that error
- **AND** the next keyword call in the same session returns its result

#### Scenario: Server answers a keyword call with a JSON-RPC error

- **WHEN** the server answers a keyword call with a JSON-RPC error
- **THEN** that call fails
- **AND** the next keyword call in the same session is sent to the server and returns its result

### Requirement: A failed session start is not kept

If starting a session fails because the server cannot be reached or the handshake fails, the client SHALL raise that error for the call that started the session and SHALL NOT keep the failed session. The next call SHALL make a new connection attempt.

#### Scenario: Server is not reachable when a session starts

- **WHEN** a session starts while the server is not reachable
- **THEN** the call that started it fails with the connection error
- **AND** the next call, made after the server became reachable, connects again and returns its result

#### Scenario: Server rejects the handshake

- **WHEN** the server rejects the handshake, for example because the requested library is not allowed
- **THEN** the call that started the session fails with the server's error
- **AND** the next call makes a new connection attempt instead of re-raising that error

### Requirement: A timed-out session start is stopped

If a session does not finish starting within `rpc_timeout`, the client SHALL stop it, closing any connection it opened, and SHALL raise a `TimeoutError`. The next call SHALL make a new connection attempt.

#### Scenario: Server accepts the connection but never answers the handshake

- **WHEN** the server accepts the connection but does not answer the handshake within `rpc_timeout`
- **THEN** the call fails with a `TimeoutError`
- **AND** the client closes the connection it opened
- **AND** the next call opens a new connection

### Requirement: A failed session start releases its resources

If starting a session fails, the client SHALL close the connection it opened before it reports the failure. For the `stdio` transport, it SHALL also wait for the server process it spawned to exit, terminating and finally killing it if it does not exit within `rpc_timeout`, before it reports the failure.

#### Scenario: Handshake fails over TCP

- **WHEN** the server rejects the handshake of a session over TCP
- **THEN** the call that started the session fails with the server's error
- **AND** the client has closed the connection

#### Scenario: Handshake fails over stdio

- **WHEN** the server spawned for a `stdio:` URI rejects the handshake
- **THEN** the call that started the session fails with the server's error
- **AND** the spawned server process has exited by the time the failure is reported

### Requirement: Calls never hang on an ended session

A keyword call on a session whose connection handling has ended, or ends before the call has started, SHALL fail with a `ConnectionError`. It SHALL NOT wait forever.

#### Scenario: Call on a session that has ended

- **WHEN** a keyword call is made on a session whose connection handling has already ended
- **THEN** the call fails at once with a `ConnectionError`

#### Scenario: Session ends before the call starts

- **WHEN** a keyword call has been handed over to the session
- **AND** the session's connection handling ends before the call has started
- **THEN** the call fails with a `ConnectionError`

### Requirement: Ending a session never raises

Ending a session SHALL NOT raise. This covers the end of its `rpc_scope`, garbage collection of the library instance, and interpreter exit. Each teardown step SHALL be bounded by `rpc_timeout`, also when the connection or the session's worker do not respond.

#### Scenario: Worker does not respond to the teardown

- **WHEN** a session is ended while its worker does not process the teardown
- **THEN** ending it returns after a bounded time
- **AND** no exception is raised

#### Scenario: Session's event loop is already closed

- **WHEN** a session is ended after its event loop has been closed
- **THEN** ending it returns without raising

### Requirement: Session errors are not printed by the worker thread

Errors that end a session's worker thread SHALL be reported to the caller that is affected by them: the call that started the session, or the keyword call that failed. They SHALL NOT be printed as an unhandled thread exception.

#### Scenario: Session fails to start

- **WHEN** a session fails to start because the server is not reachable
- **THEN** the call that started it fails with the connection error
- **AND** no unhandled exception of the session's worker thread is reported
