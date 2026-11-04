# Proposal

## Why

The peer does not follow the rules of JSON-RPC 2.0 and of the Language Server Protocol, whose framing it uses, and it reacts to malformed input in ways that cost the session or leave no trace. The probes for this proposal show:

- **Notifications get answered.** The unknown notification `robot/unknown_notification` is answered with `{"error": {"code": -32601, ...}, "id": null}`, and so is a failing handler. The LSP says that a notification "must not send a response back".
- **Header names and spacing are matched exactly.** `content-length: 42` and `Content-Length:42` are ignored, just like a missing header. The peer then reads a body of length 0, answers with a parse error and reads the real body as headers. From then on the stream is out of sync. In Robot Framework a library import ends with `Timeout waiting for JsonRpcRemote session to initialize`.
- **Malformed input closes the connection.** `Content-Length: abc` or `-5`, an unknown `charset`, a body that is not valid in its charset and a non-ASCII byte in a header all end the read loop, without a log message. A connection holds a session: the server finalizes its libraries, and the client fails all further calls unless `rpc_connect_retry_timeout` is set.
- **Problems in the client stay invisible.** Robot Framework drops what the peer logs on the client's worker thread: it reaches neither the console nor `output.xml`.
- **Responses are misread.** A success with `"error": null`, which Jackson and System.Text.Json write by default for a response class with both fields, fails the request, and Robot Framework shows `failed: None`. A response without `"jsonrpc": "2.0"` leaves the request waiting, and the peer answers the response with `-32600`.
- **A handler that returns `None` sends no `result`.** The LSP requires `null` there, and our own peer reports `Invalid response format`.
- **Invalid messages get a wrong answer or none.** `{"jsonrpc":"2.0"}` stays unanswered, `"method": []` gets `-32603 unhashable type: 'list'` without its `id`, `"method": 1` gets `-32601`, an `id` that is an object is accepted, and `params` that are neither an array nor an object reach a handler without a type, although JSON-RPC and the LSP allow only these two.
- **Sending mixes up two failures.** If the other side goes away while a handler runs, `handle_message` tries to send a second error, and the server logs `Task exception was never retrieved` with a traceback. This is the one case here that our own client and server can run into. A result that cannot be serialized is not logged, and in a batch it takes the other responses with it.
- **The charset is not named.** A peer with another `default_encoding` sends its content in that charset without saying so, and it reads a message without a charset with it, although the LSP says that such content is UTF-8.

The reports of the peer take the same path to Robot Framework as the log messages from the server, and that path has a problem of its own on the console. Since Robot Framework 7.4, `logger.write` takes `console`, and `False` keeps a message off the console. The server and the client pass `False` for every message that does not ask for the console, so on Robot Framework 7.5 a warning of a remote keyword appears in the log but not on the console. On Robot Framework 7.2 and for a local library it appears in both.

`JsonRpcInvalidRequestError` is exported but has no effect: nothing raises it, and a handler that raises it gets `-32603`. The peer's tests do not cover batches, the parse-error, invalid-request and internal-error paths of incoming messages, the `request_timeout` constructor option, or notifications registered with `attach_endpoint`.

Found in the project review of 2026-10-27 (PEER-2, PEER-3, TEST-4), in the review of `fix-rpc-error-responses` (PEER-8 to PEER-12) and in the probes for this proposal (PEER-14 to PEER-17, CLIENT-18).

## What Changes

The reference is the current LSP specification, 3.18, together with JSON-RPC 2.0. Where they say nothing, the reference library `vscode-jsonrpc` shows the way.

- **Notifications:** the peer never answers a notification. A failing handler or invalid params are reported. An unknown notification is logged at `DEBUG`.
- **Headers:** header names are matched case-insensitively, the space after the colon is optional, and whitespace around a value is tolerated. A non-ASCII byte no longer ends the read loop.
- **Messages that cannot be read:** the connection stays open. The peer reports the problem and reads on.
  - A missing, non-numeric or negative `Content-Length` gets no answer. The bytes that follow are read as the next header part.
  - An unknown `charset`, a body that is not valid in its charset and invalid JSON are answered with `-32700` and `id: null`.
  - A message above `max_message_size` is skipped and answered with `-32600` and `id: null`.
- **Reporting:** the peer logs these problems and hands them to an optional callback, like `connection.onError` in `vscode-jsonrpc`. `JsonRpcRemote` writes them through its log sink as errors to Robot Framework's log and console, also while a keyword call is waiting. An error response with `id: null` is reported the same way.
- **Invalid messages:** the peer tells messages apart as `vscode-jsonrpc` does. A request has a string `method` and a string or integer `id`, a notification has a string `method` and no `id`, and a response has an `id` and no `method`. Anything else is invalid, including `"id": null` with a `method`, `params` that are neither an array nor an object, and a message whose `jsonrpc` is not `2.0`. It is reported and answered with `-32600`, with its `id` if that is usable. `"params": null` counts as missing.
- **Responses:** the peer never answers a response, not even an invalid one. If an invalid response has the `id` of a waiting request, exactly that request fails with a message that names the problem. `"error": null` next to a `result` counts as success.
- **Results:** a handler that returns `None` sends `"result": null`.
- **Sending:** serializing and writing become separate steps. A result that cannot be serialized is logged and answered with `-32603` and its `id`, also inside a batch, where each response is serialized on its own. After a failed write the peer sends nothing more.
- **Charset:** a peer with another `default_encoding` names it in a `Content-Type` field when it sends. A message without a charset is read as UTF-8, whatever `default_encoding` says.
- **Console:** the `console` of a log message works as in Robot Framework. Without a value, `WARN` and `ERROR` go to the console and other levels do not; `true` and `false` decide it. The server and the example server leave it out unless they have a reason, and the client passes on what arrives.
- **Cleanup:** `JsonRpcInvalidRequestError` is removed.
- **Tests:** raw-stream tests for the header cases and for messages that cannot be read, batches with requests and notifications mixed, the error paths of incoming messages, `request_timeout`, `attach_endpoint` with notifications, and a Robot suite with a raw server for what a Robot user sees.
- **Docs:** the protocol page says how headers are matched, which code answers what, what happens to a message that cannot be read and what `console` means; the failures guide says where a Robot user sees such a problem; the README of `jsonrpcpeer` covers the headers, the callback and `default_encoding`.

Decisions confirmed on 2026-11-04:

- **The connection stays open, and so do waiting requests,** as in `vscode-jsonrpc`: the peer cannot tell which request an unreadable message belonged to. A keyword call has no timeout yet, so it can keep waiting; the report in the log names the reason.
- **A message above the size limit is skipped, not a reason to close.** The sender's request keeps waiting, because its `id` is unknown.
- **Batches stay.** LSP 3.18 excludes them, but JSON-RPC 2.0 provides them and the code exists.
- **Every text codec that Python knows stays,** and so does `default_encoding`. The LSP supports only UTF-8, so this goes beyond it.
- **The `jsonrpc` check stays,** because the LSP says the protocol always uses `2.0`. That `vscode-jsonrpc` does not read the field is no rule.
- **`JsonRpcEndpoint` stays untouched and untested.** It marks the planned change `add-typed-endpoints`, which comes next.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: adds requirements on notifications, header matching, messages that cannot be read, reporting, invalid messages, responses, `null` results, sending, batches, the request timeout and the charset of a message. Changes the requirements that say a message violating the framing or the size limit closes the connection.
- `client`: adds requirements that problems reported by the peer reach Robot Framework's log and console, and that a log message from the server reaches the console as that of a local library does.
- `server`: adds a requirement that the server leaves `console` out of the log messages that it forwards.

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py`: the read loop, `handle_message`, `process_single_message`, `_handle_response` and the handling of notifications; `src/JsonRpcRemote/__init__.py`: reports go to the log sink, and `console` is passed on; `packages/server/src/robot_jsonrpcremote_server/_endpoint.py` and `examples/simple-robot-jsonrpcserver`: `console` is left out by default.
- **Public API:** `JsonRpcPeer` gets an optional callback; `JsonRpcInvalidRequestError` is removed; `default_encoding` now sets only what the peer sends, and an unknown name fails when the peer is created.
- **Interoperability:** peers that send lower-case header names or `"error": null` now work, and peers no longer get answers to notifications or responses.
- **Tests:** `tests/test_peer.py`, `tests/test_client_logging.py`, `tests/test_server_end_to_end.py`, client tests against the fake server, and a new Robot suite with a raw server.
- **Docs:** `reference/protocol.mdx`, `guides/failures.mdx`, `packages/jsonrpcpeer/README.md`.
- **Order:** after `fix-peer-lifecycle` and `fix-rpc-error-responses`, which change the same file, and before `add-typed-endpoints`. `harden-server-network-defaults` still says that a larger message closes the connection; its proposal is adapted when it comes up.
