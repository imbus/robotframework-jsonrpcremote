## MODIFIED Requirements

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

## ADDED Requirements

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
