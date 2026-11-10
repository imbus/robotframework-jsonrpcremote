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

The connection counts as closed once the peer stops reading from it: the remote side closed it, reading failed, or the peer was stopped. At that point the peer SHALL fail every request still waiting for a response with a connection-closed error. No request SHALL stay unresolved after the connection has closed.

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
- **AND** reading from the connection fails, for example because the connection was reset
- **THEN** the request fails with a connection-closed error

#### Scenario: Incoming message exceeds the size limit

- **WHEN** a request is waiting for its response
- **AND** an incoming message exceeds the maximum message size of the peer
- **THEN** the connection does not count as closed
- **AND** the request keeps waiting for its response

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

When the connection closed because reading from it raised an error, the connection-closed error of an outstanding request SHALL carry that error as its cause. In all other cases (the remote side closed it cleanly or the peer was stopped) the connection-closed error SHALL have no cause.

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

#### Scenario: Peer that was called through a definition

- **WHEN** a caller has called a method through `remote` of a started peer
- **AND** the connection has closed and the caller references neither the peer nor the object from `remote`
- **THEN** the peer is freed by the next garbage collection

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

- **WHEN** the remote side answers a request with an `error` that is neither an object nor `null`
- **THEN** the request fails with a `JsonRpcResponseError` with the code `-32603` and the text of that value as its message

#### Scenario: Response with neither a result nor an error

- **WHEN** the remote side answers a request with a response that has neither a `result` nor an `error`
- **THEN** the request fails with a `JsonRpcResponseError` with the code `-32603`

### Requirement: A handler answers with an error of its choice by raising it

When a request handler raises `JsonRpcResponseError`, the peer SHALL answer the request with the code, message and data of that error. It SHALL NOT treat this as an unexpected exception. If an error response cannot be written as JSON, the peer SHALL answer the request with the code `-32603` instead, so that it does not wait forever.

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

### Requirement: A notification is never answered

The peer SHALL NOT send a response to a notification, whatever happens to it. When the handler of a notification fails or its params cannot be converted, the peer SHALL report the problem instead.

#### Scenario: Notification handler raises an unexpected exception

- **WHEN** the notification handler of the method `changed` raises `ValueError("bad value")`
- **THEN** the peer sends nothing
- **AND** the peer reports a problem that names `changed`

#### Scenario: Notification handler raises an error of its choice

- **WHEN** the notification handler of the method `changed` raises a `JsonRpcResponseError`
- **THEN** the peer sends nothing
- **AND** the peer reports a problem that names `changed` and holds the message of the error

#### Scenario: Params of a notification cannot be converted

- **WHEN** the params of a notification cannot be converted to the type of its handler
- **THEN** the peer sends nothing
- **AND** the peer reports a problem that names the method

### Requirement: An unknown notification is ignored

The peer SHALL ignore a notification for a method that it has no handler for. It SHALL log the notification at DEBUG level and SHALL neither answer nor report it.

#### Scenario: Notification for an unknown method

- **WHEN** a notification arrives for a method that the peer has no handler for
- **THEN** the peer sends nothing
- **AND** the peer logs the method at DEBUG level
- **AND** the peer reports no problem
- **AND** the next request on the same connection gets its response

### Requirement: Header fields are matched as in HTTP

The peer SHALL match the names of header fields without regard to case. The space after the colon SHALL be optional, and whitespace around a value SHALL be ignored. The peer SHALL ignore header fields that it does not know, whatever bytes they hold.

#### Scenario: Header name in lower case

- **WHEN** a message arrives with the header `content-length: 42` and 42 bytes of content
- **THEN** the peer handles the message
- **AND** the next message on the same connection is handled too

#### Scenario: Header name in upper case

- **WHEN** a message arrives with the header `CONTENT-LENGTH: 42` and 42 bytes of content
- **THEN** the peer handles the message

#### Scenario: No space after the colon

- **WHEN** a message arrives with the header `Content-Length:42` and 42 bytes of content
- **THEN** the peer handles the message

#### Scenario: Whitespace around the value

- **WHEN** a message arrives with the header `Content-Length:   42  ` and 42 bytes of content
- **THEN** the peer handles the message

#### Scenario: Charset with a different spelling

- **WHEN** a message arrives with the header `content-type: application/json; Charset="latin-1"` and content in that charset
- **THEN** the peer handles the message with its content decoded in that charset

#### Scenario: Header field that the peer does not know

- **WHEN** a message arrives with a valid `Content-Length` and the header `X-Note: anything`
- **THEN** the peer handles the message

#### Scenario: Byte outside ASCII in a header field that the peer does not know

- **WHEN** a message arrives with a valid `Content-Length` and a header field that holds a byte outside ASCII
- **THEN** the peer handles the message

### Requirement: A header part without a valid length does not end the connection

When a header part has no valid `Content-Length`, the peer SHALL report the problem, SHALL send no answer and SHALL keep reading from the connection. A valid length consists of ASCII digits only. The bytes that follow the header part SHALL be read as the next header part.

#### Scenario: Length is not a valid number

- **WHEN** a message arrives with a `Content-Length` of `abc`, `-5`, `+5`, `1.5` or `1_000`
- **THEN** the peer sends nothing
- **AND** the peer reports a problem that holds the value
- **AND** the connection stays open

#### Scenario: Length is missing

- **WHEN** a header part arrives without a `Content-Length`
- **THEN** the peer sends nothing
- **AND** the peer reports a problem that names the missing header
- **AND** the connection stays open

#### Scenario: Empty line between two messages

- **WHEN** a message is followed by an empty line that its length does not count, and then by another message
- **THEN** the peer handles both messages
- **AND** the peer reports a problem that names the missing header

#### Scenario: A request is waiting

- **WHEN** a request is waiting for its response
- **AND** a message without a valid length arrives
- **THEN** the request keeps waiting
- **AND** the request gets its response when that arrives later

#### Scenario: Content that ends with a line end

- **WHEN** a message without a valid length has content that ends with `\r\n`
- **AND** a valid message follows
- **THEN** the peer handles the valid message

#### Scenario: Content without a line end

- **WHEN** a message without a valid length has content that does not end with `\r\n`
- **AND** a valid message follows
- **THEN** the peer reports a problem for that header part too
- **AND** the connection stays open

#### Scenario: Long content without a line end

- **WHEN** a message without a valid length has content without a line end that is longer than the read buffer of the connection
- **THEN** the connection stays open
- **AND** a message that follows a line end is handled

### Requirement: A message whose content cannot be read is answered with a parse error

When the length of a message is valid but its content cannot be read, the peer SHALL report the problem, SHALL answer with the code `-32700` and `id: null`, and SHALL keep reading from the connection. This covers an unknown charset, content that is not valid in its charset, and content that is not valid JSON.

#### Scenario: Unknown charset

- **WHEN** a message arrives with `charset=nope` in its `Content-Type`
- **THEN** the response carries the code `-32700`, `id: null` and a message that holds `nope`
- **AND** the peer reports a problem that holds `nope`
- **AND** the next message on the same connection is handled

#### Scenario: Charset that is no text encoding

- **WHEN** a message arrives with `charset=hex` in its `Content-Type`
- **THEN** the response carries the code `-32700` and `id: null`
- **AND** the next message on the same connection is handled

#### Scenario: Content that is not valid in its charset

- **WHEN** a message arrives whose content holds the byte `0xFF` and whose charset is UTF-8
- **THEN** the response carries the code `-32700` and `id: null`
- **AND** the peer reports the problem
- **AND** the next message on the same connection is handled

#### Scenario: Content that is not valid JSON

- **WHEN** a message arrives whose content is `{not json`
- **THEN** the response carries the code `-32700` and `id: null`
- **AND** the peer reports the problem
- **AND** the next message on the same connection is handled

#### Scenario: Another text encoding

- **WHEN** a message arrives with `charset=latin-1` and content in that charset
- **THEN** the peer handles the message with its content decoded in that charset

#### Scenario: A request is waiting

- **WHEN** a request is waiting for its response
- **AND** a message arrives whose content cannot be read
- **THEN** the request keeps waiting
- **AND** the request gets its response when that arrives later

### Requirement: A message above the size limit is skipped

When the length of an incoming message exceeds the maximum message size of the peer, the peer SHALL skip its content without keeping it in memory, SHALL report the problem, SHALL answer with the code `-32600` and `id: null`, and SHALL keep reading from the connection.

#### Scenario: Message above the limit

- **WHEN** a message arrives whose length exceeds the maximum message size
- **THEN** the response carries the code `-32600`, `id: null` and a message that holds the length and the limit
- **AND** the peer reports the problem
- **AND** the next message on the same connection is handled

#### Scenario: Content arrives in several parts

- **WHEN** the content of a message above the limit arrives in several parts, and is longer than the read buffer of the connection
- **THEN** the next message on the same connection is handled

#### Scenario: A request is waiting

- **WHEN** a request is waiting for its response
- **AND** a message above the limit arrives
- **THEN** the request keeps waiting
- **AND** the request gets its response when that arrives later

### Requirement: The peer reports problems with incoming messages to its application

The peer SHALL log a problem with an incoming message at ERROR level. It SHALL have an option for a callback, which then also receives the text of the problem. A callback that raises an exception SHALL NOT keep the peer from reading.

#### Scenario: Peer without a callback

- **WHEN** a peer without a callback gets a message without a valid length
- **THEN** the peer logs a problem at ERROR level that holds the value

#### Scenario: Peer with a callback

- **WHEN** a peer with a callback gets a message without a valid length
- **THEN** the callback receives a text that holds the value
- **AND** the peer logs the problem at ERROR level

#### Scenario: Callback raises an exception

- **WHEN** the callback of a peer raises an exception
- **THEN** the peer logs that exception
- **AND** the next message on the same connection is handled

#### Scenario: Error response without an id

- **WHEN** the remote side sends an error response with `id: null`, the code `-32700` and the message `bad`
- **THEN** the peer reports a problem that holds the code and the message
- **AND** the peer sends nothing

#### Scenario: An error of a request handler is no problem with a message

- **WHEN** a request handler raises a `JsonRpcResponseError`
- **THEN** the callback receives nothing

### Requirement: Messages are told apart by their members

The peer SHALL treat a JSON object with a string `method` and a string or integer `id` as a request, one with a string `method` and no `id` as a notification, and one with an `id` and no `method` as a response. Anything else SHALL be an invalid message. `true` and `false` SHALL NOT count as integers.

#### Scenario: Request with a string id

- **WHEN** a message arrives with the `method` `echo` and the `id` `"7"`
- **THEN** the handler of `echo` is called
- **AND** the response carries the `id` `"7"`

#### Scenario: Request with an integer id

- **WHEN** a message arrives with the `method` `echo` and the `id` `7`
- **THEN** the handler of `echo` is called
- **AND** the response carries the `id` `7`

#### Scenario: Notification

- **WHEN** a message arrives with the `method` `changed` and no `id`
- **THEN** the notification handler of `changed` is called
- **AND** the peer sends nothing

#### Scenario: Response

- **WHEN** a request with the `id` `"1"` is waiting for its response
- **AND** a message arrives with the `id` `"1"`, a `result` and no `method`
- **THEN** the request gets that result

#### Scenario: Array as params

- **WHEN** a request arrives with the `method` `echo` and the `params` `[1, 2]`
- **THEN** the handler of `echo` gets the array

#### Scenario: Null params count as missing

- **WHEN** a request arrives with the `method` `echo` and `"params": null`
- **THEN** the handler of `echo` is called as for a request without `params`

### Requirement: An invalid message is answered with an invalid-request error

The peer SHALL NOT call a handler for an invalid message. It SHALL report the problem and SHALL answer with the code `-32600`, with the `id` of the message if that is a string or an integer, and with `id: null` otherwise. A message whose `jsonrpc` is not `2.0` SHALL be invalid.

#### Scenario: Message with neither a method nor an id

- **WHEN** the message `{"jsonrpc":"2.0"}` or `{"jsonrpc":"2.0","params":{}}` arrives
- **THEN** the response carries the code `-32600` and `id: null`
- **AND** the peer reports the problem

#### Scenario: Method that is no string, with an id

- **WHEN** the message `{"jsonrpc":"2.0","id":1,"method":[]}` arrives
- **THEN** the response carries the code `-32600` and the `id` `1`
- **AND** the peer reports the problem

#### Scenario: Method that is no string, without an id

- **WHEN** the message `{"jsonrpc":"2.0","method":1,"params":"bar"}` arrives
- **THEN** the response carries the code `-32600` and `id: null`

#### Scenario: Params that are neither an array nor an object, with an id

- **WHEN** a message arrives with the `method` `echo`, the `id` `1` and `params` that are a string, a number or a boolean
- **THEN** the response carries the code `-32600` and the `id` `1`
- **AND** the handler of `echo` is not called

#### Scenario: Params that are neither an array nor an object, without an id

- **WHEN** a message arrives with the `method` `changed`, no `id` and the `params` `"bar"`
- **THEN** the response carries the code `-32600` and `id: null`
- **AND** the notification handler of `changed` is not called

#### Scenario: Id of another type

- **WHEN** a message arrives with the `method` `echo` and an `id` that is an object, `true` or `1.5`
- **THEN** the response carries the code `-32600` and `id: null`
- **AND** the handler of `echo` is not called

#### Scenario: Null id with a method

- **WHEN** the message `{"jsonrpc":"2.0","id":null,"method":"echo"}` arrives
- **THEN** the response carries the code `-32600` and `id: null`
- **AND** the handler of `echo` is not called

#### Scenario: Message that is no object

- **WHEN** the message `1` arrives
- **THEN** the response carries the code `-32600` and `id: null`

#### Scenario: Another version with an id

- **WHEN** a message arrives with the `method` `echo`, the `id` `1` and a `jsonrpc` that is missing or `1.0`
- **THEN** the response carries the code `-32600` and the `id` `1`
- **AND** the handler of `echo` is not called

#### Scenario: Another version without an id

- **WHEN** a message arrives with the `method` `changed`, no `id` and a `jsonrpc` that is missing or `1.0`
- **THEN** the response carries the code `-32600` and `id: null`
- **AND** the notification handler of `changed` is not called

### Requirement: A response is never answered

The peer SHALL NOT answer a message that has an `id` and no `method`. If such a message is invalid and its `id` belongs to a waiting request, that request SHALL fail with a `JsonRpcResponseError` that names the problem. If it is invalid and no request waits for it, the peer SHALL report the problem.

#### Scenario: Response of another version to a waiting request

- **WHEN** a request with the `id` `"1"` is waiting for its response
- **AND** a message arrives with the `id` `"1"`, a `result` and a `jsonrpc` that is missing or `1.0`
- **THEN** the request fails right away with a `JsonRpcResponseError` with the code `-32600` and a message that names the version
- **AND** the peer sends nothing

#### Scenario: Response of another version that no request waits for

- **WHEN** a message arrives with an `id` that no request waits for, a `result` and no `jsonrpc`
- **THEN** the peer sends nothing
- **AND** the peer reports the problem

#### Scenario: Id of another type

- **WHEN** the message `{"jsonrpc":"2.0","id":{"a":1},"result":5}` arrives
- **THEN** the peer sends nothing
- **AND** the peer reports the problem

#### Scenario: Null id with neither a result nor an error

- **WHEN** the message `{"jsonrpc":"2.0","id":null}` arrives
- **THEN** the peer sends nothing
- **AND** the peer reports the problem

#### Scenario: Valid response that no request waits for

- **WHEN** a valid response arrives with an `id` that no request waits for
- **THEN** the peer sends nothing
- **AND** the peer reports no problem

### Requirement: A null error in a response is no error

The peer SHALL treat `"error": null` in a response like a missing `error`.

#### Scenario: Result next to a null error

- **WHEN** the remote side answers a request with the `result` `5` and `"error": null`
- **THEN** the request gets the result `5`

#### Scenario: Null result next to a null error

- **WHEN** the remote side answers a request with `"result": null` and `"error": null`
- **THEN** the request gets the result `None`

#### Scenario: Null error without a result

- **WHEN** the remote side answers a request with `"error": null` and no `result`
- **THEN** the request fails with a `JsonRpcResponseError` with the code `-32603`

#### Scenario: Error next to a null result

- **WHEN** the remote side answers a request with `"result": null` and an `error` with the code `-32000`
- **THEN** the request fails with a `JsonRpcResponseError` with the code `-32000`

### Requirement: A handler without a result answers with a null result

When a request handler returns `None`, the peer SHALL send a response with `"result": null`.

#### Scenario: Handler returns None

- **WHEN** the request handler of a request with the `id` `8` returns `None`
- **THEN** the response carries the `id` `8` and `"result": null`
- **AND** the caller on the other side, a peer of this package, gets the result `None`

### Requirement: A response that cannot be written fails only its own request

When the response to a request cannot be written as JSON or exceeds the maximum message size, the peer SHALL log the reason at ERROR level and SHALL answer the request with the code `-32603` and its `id`.

#### Scenario: Result cannot be written as JSON

- **WHEN** the request handler of a request with the `id` `7` returns a value that cannot be written as JSON
- **THEN** the response carries the code `-32603` and the `id` `7`
- **AND** the peer logs an error that holds the reason

#### Scenario: Result holds a float that JSON does not allow

- **WHEN** the request handler of a request with the `id` `7` returns `{"value": float("nan")}`
- **THEN** the response carries the code `-32603` and the `id` `7`
- **AND** the peer writes no message that holds `NaN`

#### Scenario: Response exceeds the maximum message size

- **WHEN** the response to a request with the `id` `7` exceeds the maximum message size of the peer
- **THEN** the response carries the code `-32603` and the `id` `7`
- **AND** the peer logs an error that holds the reason

#### Scenario: Inside a batch

- **WHEN** a batch holds a request with the `id` `1`, whose result can be written, and a request with the `id` `2`, whose result cannot
- **THEN** the answer holds the result for the `id` `1` and an error with the code `-32603` for the `id` `2`

### Requirement: A failed write sends nothing more

When writing a message to the connection fails, the peer SHALL send nothing more for that message and SHALL NOT log an error for it, because the other side is gone. asyncio SHALL NOT report the failure as never retrieved.

#### Scenario: Remote side goes away while a request handler runs

- **WHEN** a request handler is running
- **AND** the remote side closes the connection
- **AND** the handler returns
- **THEN** the peer tries no second write for that request
- **AND** the peer logs no error
- **AND** asyncio reports no exception that was never retrieved

### Requirement: A batch is answered with one array

The peer SHALL handle each element of a JSON array as a message of its own and SHALL answer with one array of the responses. If no element needs a response, the peer SHALL send nothing. An empty array SHALL be answered with the code `-32600` and `id: null`.

#### Scenario: Requests and notifications mixed

- **WHEN** a batch holds a request with the `id` `1`, a notification and a request with the `id` `2`
- **THEN** the notification handler is called
- **AND** the answer is one array with the responses for the `id` `1` and the `id` `2`

#### Scenario: Only notifications

- **WHEN** a batch holds only notifications
- **THEN** the notification handlers are called
- **AND** the peer sends nothing

#### Scenario: Failing notification

- **WHEN** a batch holds a request with the `id` `1` and a notification whose handler raises an exception
- **THEN** the answer is one array that holds only the response for the `id` `1`
- **AND** the peer reports a problem that names the method of the notification

#### Scenario: Invalid element

- **WHEN** a batch holds the element `1` and a request with the `id` `2`
- **THEN** the answer is one array with an error with the code `-32600` and `id: null`, and the response for the `id` `2`

#### Scenario: Responses

- **WHEN** a request with the `id` `"1"` is waiting for its response
- **AND** a batch arrives that holds a response with the `id` `"1"`
- **THEN** the request gets its response
- **AND** the peer sends nothing

#### Scenario: Empty batch

- **WHEN** the message `[]` arrives
- **THEN** the response carries the code `-32600` and `id: null`

### Requirement: A request timeout ends a request that waits too long

When the peer has a request timeout configured, it SHALL fail a request that gets no response in time with `TimeoutError`. The connection SHALL stay usable, and a response that arrives later SHALL be ignored.

#### Scenario: No response in time

- **WHEN** the peer has a request timeout configured
- **AND** no response to a request arrives within that time
- **THEN** the request fails with `TimeoutError`
- **AND** the next request on the same connection gets its response

#### Scenario: Response arrives after the timeout

- **WHEN** a request has failed with `TimeoutError`
- **AND** its response arrives later
- **THEN** the peer sends nothing
- **AND** the peer reports no problem

### Requirement: The charset of a message is named if it is not UTF-8

A message without a charset SHALL be read as UTF-8, whatever the default encoding of the peer is. A peer whose default encoding is not UTF-8 SHALL name it in a `Content-Type` field of every message that it sends. A peer whose default encoding is UTF-8 SHALL send no `Content-Type`.

#### Scenario: Peer with another default encoding sends a message

- **WHEN** a peer with the default encoding `latin-1` sends a message
- **THEN** the header part holds `Content-Type: application/vscode-jsonrpc; charset=latin-1`
- **AND** the content is in that charset

#### Scenario: Peer with UTF-8 sends a message

- **WHEN** a peer with the default encoding `utf-8`, `utf8` or `UTF-8` sends a message
- **THEN** the header part holds only `Content-Length`

#### Scenario: Message without a charset reaches a peer with another default encoding

- **WHEN** a peer with the default encoding `latin-1` gets a message without a charset, whose content is `ä` in UTF-8
- **THEN** the peer reads it as `ä`

#### Scenario: Two peers with different default encodings

- **WHEN** a peer with the default encoding `latin-1` and a peer with UTF-8 send each other requests that hold `ä`
- **THEN** each request and each response arrives with `ä`

#### Scenario: Unknown default encoding

- **WHEN** a peer is created with a default encoding that Python does not know
- **THEN** creating it fails with `LookupError`

### Requirement: A definition states the methods of an interface once

A definition SHALL be a subclass of `JsonRpcEndpoint`, which the `jsonrpcpeer` package exports, whose methods carry the mark `rpc_request` or `rpc_notification` with the name of the method on the wire. Each such method SHALL take one parameter, the params. Its annotations state the type of the params and, for a request, the type of the result.

#### Scenario: A method that a subclass leaves out

- **WHEN** a method of a definition is also marked `abstractmethod`
- **AND** a subclass does not override it
- **THEN** creating an object of the subclass raises a `TypeError` that names the method

#### Scenario: All methods are implemented

- **WHEN** a subclass overrides every abstract method of a definition
- **THEN** an object of the subclass can be created

#### Scenario: A method with a default implementation

- **WHEN** a marked method of a definition has a body and is not marked `abstractmethod`
- **AND** a subclass does not override it
- **THEN** an object of the subclass can be created
- **AND** when that object is attached to a peer, the method of the definition answers

### Requirement: An attached endpoint answers the methods of its definition

`attach_endpoint` SHALL register every marked method of the class of an endpoint, also a method that overrides a marked method of a base class without a mark of its own. The name on the wire SHALL come from the nearest mark in the class hierarchy. The peer SHALL call the method that the object has, and convert the params to the annotation of that method, as for every other handler.

#### Scenario: A request

- **WHEN** an object of a class that implements a definition is attached to a peer
- **AND** a request with the name from the definition arrives
- **THEN** the override is called with the params converted to the annotation of the override
- **AND** the request is answered with what the override returns

#### Scenario: A notification

- **WHEN** an object of a class that implements a definition is attached to a peer
- **AND** a notification with the name from the definition arrives
- **THEN** the override is called with the params converted to the annotation of the override

#### Scenario: The endpoint knows its peer

- **WHEN** an endpoint is attached to a peer
- **THEN** its `rpc_peer` is that peer

#### Scenario: An override without an annotation

- **WHEN** an override has no annotation for its parameter
- **AND** a request with the name from the definition arrives
- **THEN** the override is called with the params as they arrived

#### Scenario: A further subclass overrides it again

- **WHEN** a class derives from an implementation of a definition and overrides a method again
- **AND** an object of that class is attached to a peer
- **THEN** a request with the name from the definition calls the override of that class

#### Scenario: An override with a mark of its own

- **WHEN** an override carries a mark with another name
- **AND** an object of that class is attached to a peer
- **THEN** a request with the name of the override's mark calls it
- **AND** a request with the name from the definition is answered with `-32601`

#### Scenario: A static or a class method

- **WHEN** a marked method of an endpoint is a `staticmethod` or a `classmethod`
- **AND** an object of that class is attached to a peer
- **THEN** a request with the name of the mark calls the method

#### Scenario: A marked method without a separate definition

- **WHEN** a subclass of `JsonRpcEndpoint` has a marked method with a body and is the only class that names it
- **AND** an object of that class is attached to a peer
- **THEN** a request with the name of the mark calls the method

### Requirement: Calling a method of a definition sends it to the other side

`remote` of a peer SHALL return, for a definition, an object of that definition whose marked methods send to the other side of the connection. A request method SHALL wait for the response and return its result converted to the return annotation. A notification method SHALL send and return `None` without waiting for anything.

#### Scenario: A request

- **WHEN** a caller calls a request method through `remote` with params
- **THEN** the peer sends a request with the name from the definition and these params
- **AND** the call returns the result converted to the return annotation

#### Scenario: The params as a keyword

- **WHEN** a caller passes the params by the name of the parameter in the definition
- **THEN** the peer sends the same message as for a positional argument

#### Scenario: A request method without a return annotation

- **WHEN** a request method of a definition has no return annotation
- **AND** a caller calls it through `remote`
- **THEN** the call returns the result as it arrived

#### Scenario: A notification

- **WHEN** a caller calls a notification method through `remote` with params
- **THEN** the peer sends a notification with the name from the definition and these params, without an `id`
- **AND** the call returns `None`

#### Scenario: The other side answers with an error

- **WHEN** a caller calls a request method through `remote`
- **AND** the other side answers with an error
- **THEN** the call raises a `JsonRpcResponseError` with the code, message and data of that error

#### Scenario: The connection is closed

- **WHEN** the connection of a peer has closed
- **AND** a caller calls a request method or a notification method through `remote`
- **THEN** the call raises a connection-closed error

#### Scenario: The result does not fit the annotation

- **WHEN** a caller calls a request method through `remote`
- **AND** the result cannot be converted to the return annotation
- **THEN** the call raises the error of the conversion
- **AND** the connection stays open

#### Scenario: The object is of the definition

- **WHEN** a caller gets an object from `remote` for a definition
- **THEN** the object is an instance of that definition

#### Scenario: One object for each definition

- **WHEN** a caller gets an object from `remote` for a definition, and later again from the same peer
- **THEN** both are the same object
- **AND** another definition or another peer gives another object

#### Scenario: A method with a default implementation

- **WHEN** a marked method of a definition has a body and is not marked `abstractmethod`
- **AND** a caller calls it through `remote`
- **THEN** the peer sends it to the other side, and the body does not run

### Requirement: `remote` refuses what is not a definition

`remote` SHALL raise a `TypeError` when it gets something that is not a subclass of `JsonRpcEndpoint`, or a definition with a marked method that does not take exactly one parameter or is not async. The message SHALL name what it refuses.

#### Scenario: A class that is not an endpoint

- **WHEN** a caller passes a class that does not derive from `JsonRpcEndpoint` to `remote`
- **THEN** `remote` raises a `TypeError` that names the class

#### Scenario: A method with two parameters

- **WHEN** a marked method of a definition takes two parameters besides `self`
- **AND** a caller passes that definition to `remote`
- **THEN** `remote` raises a `TypeError` that names the method

#### Scenario: A plain method

- **WHEN** a marked method of a definition is a plain `def`
- **AND** a caller passes that definition to `remote`
- **THEN** `remote` raises a `TypeError` that names the method

### Requirement: Type checkers see the definition at the call

For a type checker such as `mypy` or `pyright`, the result of `remote` SHALL be an object of the definition it gets, also when the definition is abstract, and the calling project SHALL NOT need a setting of its own for that.

#### Scenario: An abstract definition

- **WHEN** a caller passes an abstract definition to `remote`
- **THEN** the type checker reports no error, and the type of the result is the definition

#### Scenario: Params of the wrong type

- **WHEN** a caller calls a method through `remote` with params of another type than the definition states
- **THEN** the type checker reports an error

#### Scenario: A method that the definition does not have

- **WHEN** a caller calls a method through `remote` that the definition does not have
- **THEN** the type checker reports an error

#### Scenario: The type of the result

- **WHEN** a caller awaits a request method through `remote`
- **THEN** the type of the result is the return annotation of the definition

### Requirement: An endpoint calls the other side of its peer

`remote` of an endpoint SHALL do the same as `remote` of the peer that it is attached to. If the endpoint has no peer, it SHALL raise a `RuntimeError` that names the class of the endpoint.

#### Scenario: An attached endpoint

- **WHEN** an attached endpoint calls a method through its `remote`
- **THEN** its peer sends it to the other side

#### Scenario: An endpoint without a peer

- **WHEN** an endpoint that was never attached, or whose `rpc_peer` was set to `None`, calls its `remote`
- **THEN** `remote` raises a `RuntimeError` that names the class of the endpoint

### Requirement: Several endpoints share one peer

A peer SHALL answer the methods of every endpoint attached to it, and SHALL call any definition through `remote`. The definition SHALL select the interface. Two handlers for the same name on the wire SHALL raise `JsonRpcMethodAlreadyRegisteredError`, which the package exports, and the message SHALL name the method.

#### Scenario: Two endpoints on one peer

- **WHEN** objects of two classes that implement different definitions are attached to one peer
- **THEN** each of them answers the methods of its definition

#### Scenario: One class implements two definitions

- **WHEN** one class derives from two definitions and implements both
- **AND** an object of that class is attached to a peer
- **THEN** it answers the methods of both

#### Scenario: One method for two definitions

- **WHEN** one class derives from two definitions that each have a method `log`, with different names on the wire, and implements `log` once
- **AND** an object of that class is attached to a peer
- **THEN** a message with either name calls that method

#### Scenario: Two handlers for one method

- **WHEN** two endpoints with a method of the same name on the wire are attached to one peer
- **THEN** attaching the second raises `JsonRpcMethodAlreadyRegisteredError`

#### Scenario: Two definitions with a method of the same Python name

- **WHEN** two definitions each have a method `log`, with different names on the wire
- **AND** a caller calls `log` through `remote` for each of them
- **THEN** each call sends the name from its own definition

#### Scenario: Both directions on one connection

- **WHEN** one side implements a definition and calls another, and the other side does the opposite
- **THEN** the calls of both sides get their responses on the one connection

#### Scenario: A definition that the peer also implements

- **WHEN** an object that implements a definition is attached to a peer
- **AND** a caller calls a method of that definition through `remote` of that peer
- **THEN** the call goes to the other side, and the attached object is not called

### Requirement: A handler can be a plain function

A request or notification handler SHALL be an async function or a plain function. The peer SHALL call a plain function on its event loop, once, with the params converted as for any handler, and SHALL use what it returns as the result. If what it returns is awaitable, the peer SHALL wait for it.

#### Scenario: A plain function answers a request

- **WHEN** a plain function is registered as the handler of a request
- **AND** that request arrives
- **THEN** the function is called once with the params converted to its annotation
- **AND** the request is answered with what the function returns

#### Scenario: A plain function that takes the peer

- **WHEN** a plain function with the parameters `(peer, params)` is registered as the handler of a request
- **AND** that request arrives
- **THEN** the function is called with the peer and the converted params

#### Scenario: A plain function handles a notification

- **WHEN** a plain function is registered as the handler of a notification
- **AND** that notification arrives
- **THEN** the function is called once, and no problem is reported

#### Scenario: A plain function raises an unexpected exception

- **WHEN** a plain function that handles a request raises `ValueError("bad value")`
- **THEN** the request is answered with `-32603` and that message
- **AND** the peer logs an error that names the method

#### Scenario: A plain function raises an error of its choice

- **WHEN** a plain function that handles a request raises a `JsonRpcResponseError`
- **THEN** the request is answered with the code, message and data of that error

#### Scenario: A plain function returns an awaitable

- **WHEN** a plain function that handles a request returns a coroutine
- **THEN** the peer waits for it, and the request is answered with its result

#### Scenario: A marked plain method

- **WHEN** a subclass of `JsonRpcEndpoint` has a plain method with a mark and no separate definition
- **AND** an object of that class is attached to a peer
- **THEN** a message with the name of the mark calls the method

#### Scenario: A plain method as an override of a definition

- **WHEN** a class overrides an `async def` of a definition with a plain method
- **THEN** a type checker such as `mypy` or `pyright` reports an error

### Requirement: New notifications fail after the connection closed

Once the connection has closed, the peer SHALL reject every new notification immediately with a connection-closed error and SHALL NOT write it to the connection, as it does for a request.

#### Scenario: Notification sent after the connection closed

- **WHEN** the connection of a peer has closed
- **AND** a caller sends a notification
- **THEN** the call raises a connection-closed error that names the method
- **AND** nothing is written to the connection

### Requirement: A process can connect over its stdin and stdout

The `jsonrpcpeer` package SHALL export the coroutine function `open_stdio_connection()`. It SHALL return an `asyncio.StreamReader` and an `asyncio.StreamWriter` for the stdin and stdout of the current process, which a `JsonRpcPeer` can use like the pair of any other connection.

#### Scenario: A peer answers a request

- **WHEN** a process runs a `JsonRpcPeer` on the pair from `open_stdio_connection()`, and the process that started it sends a request over the process's stdin
- **THEN** the handler of the peer runs, and the response arrives on the process's stdout

#### Scenario: Large messages

- **WHEN** 4 MiB are sent to the process over its stdin, and it sends them back over the pair
- **THEN** all bytes arrive unchanged

### Requirement: What is written to stdout appears on stderr

After `open_stdio_connection()` has returned, file descriptor 1 SHALL refer to the stderr of the process, and the connection SHALL use a private duplicate of the original stdout. Only what is written to the returned writer SHALL reach the original stdout. This has no option to turn it off.

#### Scenario: print

- **WHEN** the process calls `print()` without flushing
- **THEN** the text appears on stderr at the end of its line, while the process still runs
- **AND** it does not appear on the original stdout

#### Scenario: Direct write to file descriptor 1

- **WHEN** the process calls `os.write(1, ...)`, or writes to `sys.__stdout__`
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: Child process

- **WHEN** the process starts a child process that inherits stdout, with `subprocess` or `os.system()`, and the child writes to its stdout
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: Text buffered before the call

- **WHEN** `sys.stdout` still holds text that was not flushed when the process calls `open_stdio_connection()`
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: After the connection has closed

- **WHEN** the writer has been closed and the process calls `print()`
- **THEN** the text appears on stderr without an error

### Requirement: stdin no longer delivers the data of the connection

After `open_stdio_connection()` has returned, file descriptor 0 SHALL refer to the null device, and the connection SHALL use a private duplicate of the original stdin. Only the returned reader SHALL receive what arrives on the original stdin.

#### Scenario: Reading stdin in the process

- **WHEN** data for the connection is waiting on the original stdin and the process calls `input()`, `sys.stdin.read()` or `os.read(0, ...)`
- **THEN** `input()` raises `EOFError`, and the other two return nothing
- **AND** the returned reader still receives the data

#### Scenario: Reading stdin in a child process

- **WHEN** the process starts a child process that inherits stdin, and the child reads it
- **THEN** the child sees the end of its input at once
- **AND** the returned reader still receives the data

### Requirement: A child process does not keep the connection open

The private duplicates SHALL NOT be inherited by child processes, so that the other end of the connection sees its end when the process ends, even if a child process still runs.

#### Scenario: Process ends while a child process runs

- **WHEN** the process starts a child process that keeps running, and then exits
- **THEN** the reader at the other end of the process's stdout sees the end of the stream at once, and not when the child process ends

### Requirement: The connection is refused if stdin or stdout cannot be used

`open_stdio_connection()` SHALL raise a `RuntimeError` that names the reason if stdin cannot be watched for input, as a pipe or a socket can, or if stdin or stdout is closed. It SHALL then leave stdin and stdout as they are. A pipe whose writing end is already closed is a valid stdin.

#### Scenario: stdin is the null device

- **WHEN** stdin is `/dev/null`
- **THEN** the error states that stdio mode needs a stdin that can be watched for input, such as a pipe, and that stdin is a character device

#### Scenario: stdin is a regular file

- **WHEN** stdin is a regular file
- **THEN** the error states the same need, and that stdin is a regular file

#### Scenario: stdin is closed

- **WHEN** file descriptor 0 is closed
- **THEN** the error states the same need, and that stdin is closed

#### Scenario: stdout is closed

- **WHEN** file descriptor 1 is closed
- **THEN** the error states that stdio mode needs an open stdout

#### Scenario: The standard streams stay after a refusal

- **WHEN** the call has been refused because of stdin, and the process then writes to its stdout
- **THEN** the text appears on the original stdout

#### Scenario: stdin is a pipe that is already closed

- **WHEN** stdin is a pipe whose writing end is already closed
- **THEN** the call returns, and the reader sees the end of the stream

### Requirement: A closed stderr does not get in the way of the connection

If the stderr of the process is closed, `open_stdio_connection()` SHALL work as usual, with what is written to stdout discarded, and SHALL NOT let its private duplicates take the place of file descriptor 2.

#### Scenario: Process without a stderr

- **WHEN** file descriptor 2 is closed, the process calls `open_stdio_connection()` and then writes to its stdout
- **THEN** messages still pass in both directions, and only what is written to the returned writer reaches the original stdout
- **AND** a write to file descriptor 2 does not reach the connection

### Requirement: The pair from stdin and stdout closes like the pair of a socket

Closing the returned writer SHALL end the connection in both directions, and `writer.wait_closed()` SHALL wait for that. The end of the input SHALL leave the writer usable. An error that ends the connection SHALL NOT be reported as never retrieved.

#### Scenario: The process closes the writer

- **WHEN** the process writes data, calls `writer.close()` and awaits `writer.wait_closed()`
- **THEN** the wait returns, the data arrives on the original stdout, the other end sees the end of the stream, and the reader sees the end of the stream too

#### Scenario: The input ends first

- **WHEN** the other end closes the process's stdin, and the process then writes data and closes the writer
- **THEN** the reader sees the end of the stream, and the data arrives on the original stdout

#### Scenario: The other end goes away

- **WHEN** the other end closes the reading end of the process's stdout while the process keeps writing
- **THEN** `writer.drain()` raises a `ConnectionError`, and the reader sees the end of the stream
- **AND** asyncio reports no exception as never retrieved

### Requirement: On Windows an overlapped pipe goes through I/O completion ports

On Windows, `open_stdio_connection()` SHALL use an overlapped pipe on stdin or stdout through the proactor event loop, without a thread. The requirements for the connection over stdin and stdout SHALL hold there as on other platforms.

#### Scenario: Large messages

- **WHEN** a process on Windows with overlapped pipes on stdin and stdout calls `open_stdio_connection()`, and 4 MiB are sent to it over its stdin, and it sends them back over the pair
- **THEN** all bytes arrive unchanged

#### Scenario: No thread for the streams

- **WHEN** such a process calls `open_stdio_connection()` and exchanges a message
- **THEN** the number of threads of the process is the same as before the call

### Requirement: On Windows a synchronous pipe gets a thread of its own

On Windows, `open_stdio_connection()` SHALL read a synchronous pipe on stdin in a thread of its own, and write a synchronous pipe on stdout in another, so that the event loop never waits for such a pipe. This SHALL work on any event loop. The requirements for the connection over stdin and stdout SHALL hold there as for overlapped pipes.

#### Scenario: Pipes that subprocess creates

- **WHEN** a process started with `subprocess.PIPE` for stdin and stdout calls the function, and 4 MiB are sent to it over its stdin, and it sends them back over the pair
- **THEN** all bytes arrive unchanged
- **AND** the process has two threads more than before the call

#### Scenario: Node's default pipes

- **WHEN** a process started by Node's `child_process.spawn()` without a `stdio` option, as VS Code starts a debug adapter, runs a `JsonRpcPeer` on the pair, and Node sends it a request
- **THEN** Node receives the response

#### Scenario: Only stdin is synchronous

- **WHEN** stdin is a synchronous pipe and stdout an overlapped pipe
- **THEN** the process has one thread more than before the call, and messages pass in both directions

#### Scenario: The other end reads slowly

- **WHEN** the process writes 4 MiB while the other end does not read for 2 seconds
- **THEN** a timer of the event loop that is due in that time runs on time
- **AND** all bytes arrive once the other end reads

#### Scenario: Closing ends the threads

- **WHEN** the process closes the writer and awaits `writer.wait_closed()`, while the other end keeps its end of stdin open and sends nothing
- **THEN** the reader sees the end of the stream, and both threads have ended within 1 second

#### Scenario: A child process does not wait for the next message

- **WHEN** the process starts a child process while the thread waits for input on stdin, and the next message comes only 5 seconds later
- **THEN** the child process has run and ended within 2 seconds

#### Scenario: Selector event loop

- **WHEN** the function is called on a selector event loop with synchronous pipes on stdin and stdout
- **THEN** messages pass in both directions

### Requirement: On Windows the moved streams also reach the standard handles

On Windows, the move of stdin and stdout SHALL also change the handles that `GetStdHandle()` returns, which is what native code and child processes use.

#### Scenario: Native write to the standard output handle

- **WHEN** code calls `WriteFile()` on the handle from `GetStdHandle(STD_OUTPUT_HANDLE)`
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: Child process that writes and reads

- **WHEN** the process starts a child process with `subprocess` or `os.system()` that writes to its stdout and reads its stdin
- **THEN** the text appears on stderr and not on the original stdout
- **AND** the child sees the end of its input at once
- **AND** the returned reader still receives the data of the connection

### Requirement: On Windows no other handle to the pipes reaches a child process

On Windows, `open_stdio_connection()` SHALL keep child processes from inheriting any handle of the process to its stdin and stdout pipes, also one that the process inherited besides its standard handles, as CPython's launcher of a venv hands them down.

#### Scenario: Handles that a launcher handed down

- **WHEN** the process has inherited further handles to its stdin and stdout pipes besides its standard handles, calls the function, starts a child process that inherits all inheritable handles, and then exits while the child process runs
- **THEN** the other end of its stdout sees the end of the stream at once

### Requirement: On Windows the connection is refused for a stdin that is no pipe, and for an overlapped pipe without a proactor

On Windows, `open_stdio_connection()` SHALL raise a `RuntimeError` that names the reason if stdin is not a pipe, or if stdin or stdout is an overlapped pipe while the running event loop is not a proactor event loop. It SHALL then leave stdin and stdout as they are.

#### Scenario: Null device on stdin

- **WHEN** stdin is the null device
- **THEN** the error states that stdio mode needs a stdin that can be watched for input, such as a pipe, and that stdin is a character device

#### Scenario: Console on stdin

- **WHEN** stdin is a console
- **THEN** the error states the same need, and that stdin is a character device

#### Scenario: Overlapped pipes on a selector event loop

- **WHEN** the function is called on a selector event loop, and stdin and stdout are overlapped pipes
- **THEN** the error states that stdio on Windows needs the proactor event loop for overlapped pipes

### Requirement: A process can be started with a connection over its stdin and stdout

The `jsonrpcpeer` package SHALL export the coroutine function `create_stdio_subprocess(*argv, **kwargs)`. It SHALL start the process and return it with an `asyncio.StreamReader` for its stdout and an `asyncio.StreamWriter` for its stdin. On Windows, both SHALL be overlapped pipes, on other platforms ordinary pipes. Further arguments SHALL go to `asyncio.create_subprocess_exec()`.

#### Scenario: A process that uses the connection function

- **WHEN** a process started this way calls `open_stdio_connection()` and runs a `JsonRpcPeer`, and the caller sends a request over the returned pair
- **THEN** the caller receives the response

#### Scenario: A process with plain blocking reads and writes

- **WHEN** a process started this way reads `sys.stdin.buffer` and writes `sys.stdout.buffer` with one reader and one writer, without `open_stdio_connection()`
- **THEN** all bytes pass in both directions, 4 MiB included

#### Scenario: Further arguments

- **WHEN** the caller passes `stderr=asyncio.subprocess.PIPE` and `cwd`
- **THEN** the process runs in that directory, and the caller can read its stderr from the returned process

#### Scenario: Closing the writer

- **WHEN** the caller closes the writer
- **THEN** the process sees the end of its input
- **AND** the reader of the caller still receives what the process writes, until the process has closed its stdout

#### Scenario: Output before the end of the process

- **WHEN** the process writes its output in many small blocks and ends before the caller reads it
- **THEN** the caller reads all of it

#### Scenario: Command that cannot be started

- **WHEN** the command does not exist
- **THEN** the call raises `FileNotFoundError`, and on Windows no handle of the pipes stays open

### Requirement: On Windows a process started without a console opens no window

On Windows, `create_stdio_subprocess()` and `create_pipe_subprocess()` SHALL start the process without a window if the caller has no console, unless the caller passes `creationflags`. If the caller has a console, the process SHALL share it.

#### Scenario: Caller without a console

- **WHEN** a caller without a console starts a process
- **THEN** the process is started with the flag `CREATE_NO_WINDOW`

#### Scenario: Caller with a console

- **WHEN** a caller with a console starts a process
- **THEN** the process is started without that flag, so that it writes to that console and gets its Ctrl+C

#### Scenario: Caller passes creationflags

- **WHEN** a caller without a console passes `creationflags`
- **THEN** the process is started with exactly these flags

### Requirement: A pipe name means a named pipe on Windows and a socket file elsewhere

The `jsonrpcpeer` package SHALL export the function `pipe_address(name)`, and its functions for pipes SHALL resolve every name with it. On Windows, it SHALL return a name that starts with `\\` or `//` unchanged and put `\\.\pipe\` before any other name. On other platforms, it SHALL return the name unchanged, as the path of a Unix domain socket, relative to the working directory unless it is absolute. An empty name SHALL raise `ValueError`.

#### Scenario: Bare name on Windows

- **WHEN** `pipe_address("robot")` is called on Windows
- **THEN** it returns `\\.\pipe\robot`

#### Scenario: Full name on Windows

- **WHEN** a pipe server listens on `\\.\pipe\robot`, and processes on Windows connect with the name `\\.\pipe\robot` and with `//./pipe/robot`
- **THEN** the server accepts both connections

#### Scenario: A bare name never opens a file on Windows

- **WHEN** a regular file `robot` exists in the working directory on Windows, no server listens on `\\.\pipe\robot`, and a process connects with the name `robot`
- **THEN** the connection fails with `FileNotFoundError`, and the file stays closed

#### Scenario: Relative path on other platforms

- **WHEN** a pipe server on Linux or macOS listens on the name `robot.sock`
- **THEN** its socket file is `robot.sock` in the working directory, and a process in the same directory connects with that name

#### Scenario: Empty name

- **WHEN** `pipe_address()` is called with an empty name
- **THEN** it raises `ValueError`

### Requirement: A process can listen on a pipe, and others can connect to it

The package SHALL export the coroutine functions `start_pipe_server(client_connected_cb, name)` and `open_pipe_connection(name)`, after `asyncio.start_unix_server()` and `asyncio.open_unix_connection()`. The server SHALL be an `asyncio.AbstractServer` that calls `client_connected_cb` with a reader and a writer for each connection, and `open_pipe_connection()` SHALL return a reader and a writer. Both SHALL use named pipes on Windows and Unix domain sockets elsewhere.

#### Scenario: Messages in both directions

- **WHEN** a process connects to a pipe server, and both sides run a `JsonRpcPeer` over their reader and writer
- **THEN** a request and its response pass, and so does a message of 1 MiB in each direction

#### Scenario: Several connections

- **WHEN** two processes connect to the same pipe server at the same time
- **THEN** each gets a connection of its own, and the messages of one do not reach the other

#### Scenario: Nobody listens

- **WHEN** a process connects to a name for which there is no pipe and no socket file
- **THEN** `open_pipe_connection()` raises `FileNotFoundError`, and its message names the address

#### Scenario: An event loop without pipes on Windows

- **WHEN** `start_pipe_server()` or `open_pipe_connection()` runs on Windows on an event loop that is not a proactor event loop
- **THEN** it raises `RuntimeError`, and the message names the proactor event loop

### Requirement: A pipe server refuses a name that is in use

`start_pipe_server()` SHALL raise an `OSError` with `errno.EADDRINUSE` whose message names the address if a server already listens on the name, on every platform, and the server already there SHALL keep working. On platforms other than Windows, it SHALL replace a socket file on which nobody listens.

#### Scenario: A server listens on the name

- **WHEN** a pipe server is started on a name that another pipe server listens on
- **THEN** the start raises `OSError` with `errno.EADDRINUSE`, and the message names the address
- **AND** the first server still accepts new connections

#### Scenario: The socket file of a server that was killed

- **WHEN** on Linux or macOS a pipe server is started on the path of a socket file that a killed server left behind
- **THEN** the server starts and accepts connections

#### Scenario: A regular file at the path

- **WHEN** on Linux or macOS a pipe server is started on the path of a regular file
- **THEN** the start raises `OSError` whose message names the path, and the file is unchanged

### Requirement: Closing a pipe server stops it listening and leaves its connections open

After `close()` of a pipe server, a new connection to its name SHALL NOT reach the server, and the connections that the server had accepted SHALL stay open until their writers are closed. A new connection SHALL fail; on Windows, it waits while an accepted connection is open, because the pipe is busy then, and fails once those connections have ended. On platforms other than Windows, closing SHALL remove the socket file.

#### Scenario: An accepted connection after close

- **WHEN** a pipe server has accepted a connection and is closed
- **THEN** messages still pass over that connection in both directions

#### Scenario: A new connection after close

- **WHEN** a process connects to the name of a pipe server that was closed and has no open connections
- **THEN** the connection fails with `FileNotFoundError`

#### Scenario: The socket file after close

- **WHEN** a pipe server on Linux or macOS is closed, on every supported Python version
- **THEN** its socket file is gone

### Requirement: A process can be started with a connection over a pipe

The package SHALL export the coroutine function `create_pipe_subprocess(*argv, **kwargs)`. It SHALL listen on a new address, start the process with `--pipe=<address>` as its last argument, return it with a reader and a writer for the first connection to that address, and then stop listening and remove the address. Off Windows, the address SHALL lie in a new directory that only the current user can enter. Further arguments SHALL go to `asyncio.create_subprocess_exec()`.

#### Scenario: A process that connects with the connection function

- **WHEN** a process started this way connects to the address of its last argument with `open_pipe_connection()` and runs a `JsonRpcPeer`, and the caller sends a request over the returned reader and writer
- **THEN** the caller receives the response

#### Scenario: A process with plain blocking reads and writes

- **WHEN** a process started this way connects to the address with blocking I/O, without asyncio, and reads each request before it writes its response
- **THEN** the messages pass in both directions

#### Scenario: Only the first connection

- **WHEN** the process has connected, and another process connects to the same address
- **THEN** that connection never reaches the caller
- **AND** on Linux and macOS it fails, and the directory of the address is gone
- **AND** on Windows it waits while the first connection is open, because the pipe is busy, and fails with `FileNotFoundError` once that connection has ended

#### Scenario: A process that exits before it connects

- **WHEN** the process exits with exit code 3 before it connects
- **THEN** the call raises `ConnectionError` whose message names the exit code, and the address is gone

#### Scenario: Cancelled while it waits for the connection

- **WHEN** the call is cancelled before the process has connected
- **THEN** the process has ended, and the address is gone

#### Scenario: Command that cannot be started

- **WHEN** the command does not exist
- **THEN** the call raises `FileNotFoundError`, and the address is gone

#### Scenario: Further arguments

- **WHEN** the caller passes `stdin=asyncio.subprocess.DEVNULL` and `cwd`
- **THEN** the process runs in that directory, and reading its stdin gives the end of the input at once
