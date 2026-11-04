# Design

## Context

See `proposal.md` for the motivation and the decisions, and the delta specs for the behavior. These facts shape the approach:

- `io_loop` in `peer.py` reads headers and content in one loop and ends on any exception. `handle_message` parses, dispatches and sends, and its last `except Exception` catches failures of serializing and of writing alike.
- The peer logs through a module logger. On the client it runs on the session's worker thread, where Robot Framework drops log messages. `_LogSink` exists for that reason.
- `StreamReader.readuntil` raises `LimitOverrunError` beyond its limit, 64 KiB by default, and keeps the bytes in its buffer. Neither the server nor the client changes the limit.
- The resources of a client session are held by its finalizer, so nothing reachable from them may refer to the session.
- `logger.write` takes `console` since Robot Framework 7.4. `None` is its default and leaves the choice to the level; `False` keeps even a warning off the console.

The approach was tried out as a prototype on copies of the packages. Over real sockets the scenarios of the delta specs behave as described. All 157 Robot tests pass against it, and 7 of the 708 unit tests fail, those named under decision 11. What a Robot user sees was checked on Robot Framework 7.5 and 7.2.

## Goals / Non-Goals

**Goals:**

- Nothing in an incoming message ends the read loop. Only the end of the connection and a failure to read from it do.
- One path reports every problem with an incoming message that the peer cannot answer to the one who waits for it.
- A failure to serialize a response and a failure to write it are handled separately.

**Non-Goals:**

- Timeouts for keyword calls. They are a topic of their own (CLIENT-1); this change only makes sure that a waiting call has a reason in the log.
- Typed endpoints: `add-typed-endpoints` comes next and leaves this design as it is.
- Finding the next message by searching for a header in unreadable bytes. `vscode-jsonrpc` does not do it either, and a body can hold any text.
- Forwarding the `console` value of Robot Framework's own message, for example of `logger.info(..., also_console=True)`. That needs a change to the subscriber interface and works only from Robot Framework 7.4 on, and the reported problem does not need it.

## Decisions

### 1. The read loop reads one message per round

`io_loop` calls a new `_read_message` in its loop, which reads a header part, checks the length, reads the content, decodes it and starts handling it. What is left to end the loop are the errors of the stream itself: `IncompleteReadError` and connection errors. Their handling stays as it is.

A header line is decoded as ASCII with `errors="replace"`, because the content of a message with a bad length is read as header lines and can hold anything. A name is matched with `partition(":")`, `strip()` and `lower()`, as `vscode-jsonrpc` does. A line without a colon is a field that the peer does not know. Only `b"\r\n"` ends a header part.

**Alternative:** closing the connection on bad input, as the first version of the proposal said. A connection holds a session, so this was rejected.

### 2. A line above the reader's limit is dropped

On `LimitOverrunError`, the peer drops `error.consumed` bytes with `readexactly` and goes on reading to the end of the line. It returns `None` for such a line instead of `""`, so that the line does not count as the end of the header part. A valid `Content-Length` before or after a very long unknown field still works. This takes about eight lines and removes the last case in which the content of a message would end the connection.

**Alternative:** a higher limit only moves the problem.

### 3. A valid length matches `[0-9]{1,18}`

`int()` also takes `+5`, `1_000` and the digits of other scripts, and raises for more than 4300 digits. One regular expression rules all of that out in one place, and no message has more than 18 digits of length.

### 4. One path for problems: a log entry and an optional callback

`JsonRpcPeer` gets the keyword-only option `on_problem: Callable[[str], None] | None`, the counterpart of `connection.onError`. `_report_problem` logs the text at ERROR level, with the traceback where there is one, and then calls the callback. An exception of the callback is logged and goes no further.

It is used for invalid and missing lengths, content that cannot be read, messages above the limit, invalid messages and responses, failing notification handlers, params of a notification that cannot be converted, and error responses with `id: null`. It is not used for failures of request handlers, because their caller gets an answer, and not for a valid response that no request waits for, which is normal after a timeout.

In the client, `_start_peer` passes `functools.partial(_report_peer_problem, log_sink, uri)`. It is a module function and not a bound method, because the resources hold the peer and the finalizer holds the resources: a bound method would keep the session alive. The message is written at level ERROR through `_LogSink`, which already handles the worker thread and the time between keyword calls. The server passes nothing, because its log is the right place.

**Alternatives:**
- A `logging.Handler` on the peer's logger in the client: the logger is shared by the whole module, so one session would see the problems of all others.
- An event with exception objects: the only consumer displays a text.

### 5. An unreadable message leaves waiting requests alone

This is the decision of the proposal, as in `vscode-jsonrpc`. Only a response whose `id` matches a waiting request can fail that request, because then the peer knows which one is meant.

### 6. Answers to unreadable messages run as tasks

The read loop must not block on a full write buffer. `-32700` and `-32600` are therefore sent from a task, as `handle_message` is, tracked in `_inflight` and cancelled by `stop()`. A message above the limit is answered first and skipped afterwards, so that a slow sender does not delay the answer. Skipping reads pieces of at most 64 KiB and drops them. If the connection ends meanwhile, skipping returns, and the next read sees the end.

### 7. Messages are told apart in one place

`process_single_message` decides in this order: not an object, invalid; an `id` and no `method`, `_handle_response`; wrong `jsonrpc`, invalid; `method` not a string, invalid; no `id`, notification; `id` not usable, invalid; otherwise a request. `_is_usable_id` accepts `str` and `int`, but not `bool`, which is a subclass of `int`.

`_handle_response` becomes synchronous and returns nothing, so it cannot answer. A request that has just timed out can still be registered while its future is already done, so the peer treats a done future as no waiting request. `error` is checked with `is not None` and `result` with `in`, which covers both null cases of the spec.

**Alternative:** keeping the `match` statement. Its case for `"error"` also matches `null`, which is the bug at hand, and the order of the cases hides the rules.

### 8. Serializing and writing are separate steps

- `_encode_message` serializes, encodes and checks the size, and raises if any of that fails.
- `_write_frame` writes header and content in one synchronous step, which `_endpoint.py` relies on for the order of log messages.
- `_send_message` combines the two for requests and notifications, and raises to its caller as before.
- `_encode_response` catches failures of `_encode_message`, logs them and encodes an error response for the same `id` instead. That fallback skips the size check and uses `backslashreplace`, so it cannot fail for the same reason.
- `_write_answer` sends an answer. If that fails, the other side is gone: it logs at DEBUG level and sends nothing more.

The last `except Exception` of `handle_message` goes away, because it is what mixed the two failures. Parsing catches `ValueError` and `RecursionError`, because a huge integer and deep nesting do not raise `JSONDecodeError`; both were tried in the prototype and get `-32700`.

### 9. In a batch, each response is encoded on its own

Each response goes through `_encode_response`, and the texts are joined into the array. One result that cannot be written then does not take the others with it. The size limit applies to each response, not to the array.

### 10. `console` is passed through, and `result` has no default

`_LogSink.submit` and `_write_log` take `console: bool | None`. The client passes `params.console` as it arrives, instead of `params.console or False`. `log()` of the server endpoint and of the example server default to `None`, so `console` is left out on the wire. Before Robot Framework 7.4, `_write_log` writes to the console separately only for `True`, and Robot Framework writes warnings to the console by itself. Reports of the peer pass `None` as well.

`JsonRpcResponse.result` loses its default. `as_json` leaves out a field that is `None` and has a default, whatever its metadata says, so `force_json`, as the backlog suggested, does not help. A field without a default is always written; the prototype sends `"result":null`.

### 11. Tests

Raw-stream tests in `tests/test_peer.py` feed bytes to a `StreamReader` and read what a fake writer got. Client tests extend `tests/test_client_logging.py` and the fake server. A new Robot suite gets a raw server of its own on the next free fixed port, 8285, because only a raw server can send broken frames. It checks what a Robot user sees: the error in the execution errors and on the console, a keyword that passes after a report, and an import with `"error": null`.

These existing tests change on purpose:

- `test_empty_batch_returns_error`, `test_request_with_extra_field_error_code` and the two tests of the traceback of a message that cannot be parsed replace `_send_message` and move to reading what is written. The test of a message that cannot be parsed now expects a report instead of no log.
- `test_oversized_incoming_message_fails_the_request_without_a_cause` turns into its opposite: the request keeps waiting.
- `test_error_that_a_notification_handler_raises_is_not_logged` now expects a report, because nobody else can learn of the error.
- `test_forwarded_message_keeps_its_level_and_html_and_is_not_for_the_console` expects no `console` instead of `False`.

## Risks / Trade-offs

- [A keyword call can wait forever if its response is lost in an unreadable message] → This is the decision of the proposal. The error in Robot Framework's log and on the console names the reason, and keyword timeouts come with CLIENT-1.
- [A foreign peer whose content does not end with `\r\n` does not get back in step after a bad length: every later message is reported, and calls keep waiting] → `vscode-jsonrpc` behaves the same. The report names the bad header, and the fix belongs to the sender. Peers of this package end their content with `\r\n` and get back in step at once.
- [A broken peer can fill the log with errors, one per header part] → A client or server that sends junk can already fill the log. Limits belong to `harden-server-network-defaults`.
- [The sender of a message above the size limit keeps waiting, because its `id` is unknown] → It gets `-32600` with `id: null`, and the client of this package shows that in Robot Framework's log. `harden-server-network-defaults` has to adapt its proposal, which still says that a larger message closes the connection.
- [An array of responses that is larger than the size limit as a whole is still sent] → Nothing in this project sends batches. Checking the array would need a second fallback for no known use.
- [Before Robot Framework 7.4, `console: false` cannot keep a warning off the console] → That version has no such option, and Robot Framework writes warnings to the console by itself. The spec says so.

## Migration Plan

Nothing to migrate: the project is in pre-alpha, and client and server ship together. Whoever used `JsonRpcInvalidRequestError` in a handler uses `JsonRpcResponseError(JsonRpcErrorCode.INVALID_REQUEST, ...)` instead.
