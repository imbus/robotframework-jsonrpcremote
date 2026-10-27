# Spec Delta

## ADDED Requirements

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
