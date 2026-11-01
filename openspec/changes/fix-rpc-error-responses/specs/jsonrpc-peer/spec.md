# Spec Delta

## ADDED Requirements

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

When a request handler raises `JsonRpcResponseError`, the peer SHALL answer the request with the code, message and data of that error. It SHALL NOT treat this as an unexpected exception.

#### Scenario: Handler raises an error with a code

- **WHEN** a request handler raises a `JsonRpcResponseError` with the code `-32001` and the message `gone`
- **THEN** the response carries the code `-32001` and the message `gone`, without data
- **AND** the peer logs no error

#### Scenario: Handler raises an error with data

- **WHEN** a request handler raises a `JsonRpcResponseError` with the data `details`
- **THEN** the response carries the data `details`

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
