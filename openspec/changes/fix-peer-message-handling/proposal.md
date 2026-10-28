# Proposal

## Why

The peer breaks JSON-RPC 2.0 in one place, and it handles malformed headers in ways that desynchronize the stream or end the connection without a trace:

- **Notifications get answered.** When a notification handler fails or the method is unknown, the peer sends an error response with `"id": null`. JSON-RPC 2.0 forbids any response to a notification. A raw-socket test confirms it: the unknown notification `robot/unknown_notification` is answered with `{"error": {"code": -32601, ...}, "id": null}`. In practice, when the client's log handler failed on Robot Framework 7.1 to 7.3, the client sent error responses to the server.
- **The `Content-Length` header is matched case-sensitively and with exactly one space.** `content-length: 42` is ignored, so the peer reads a body of length 0, answers with a parse error, and then reads the real body as headers. From then on the stream is out of sync.
- **A non-numeric length** such as `Content-Length: abc` closes the connection without any diagnostic.
- **An unknown `charset`** in the `Content-Type` header goes unchecked to `bytes.decode()`, which ends the connection.

The peer's tests do not cover batches, the parse-error, invalid-request and internal-error paths of incoming messages, the `request_timeout` constructor option, or notifications registered with `attach_endpoint`. `JsonRpcEndpoint`, a decorator-based handler registry in `peer.py`, is neither tested nor exported, and nothing uses it.

Found in the project review of 2026-10-27 (items PEER-2, PEER-3 and TEST-4).

## What Changes

- **Notifications:** the peer never sends a response to a notification. A failing or unknown notification is logged instead.
- **Headers:** header names are matched case-insensitively, and whitespace around a value is tolerated.
- **Invalid length:** a missing, non-numeric or negative `Content-Length` closes the connection with a logged error that names the problem. Pending requests fail with the connection-closed error, as for any closed connection.
- **Unknown charset:** a body in an unknown charset is answered with a parse error (`-32700`), and the connection stays usable, because its length was valid.
- **Tests:** batches with requests and notifications mixed, the error paths of incoming messages, `request_timeout`, `attach_endpoint` with notifications, and raw-stream tests for the header cases.
- **Cleanup:** `JsonRpcEndpoint` is removed.

Assumptions recorded for review:

- `JsonRpcEndpoint` is removed rather than tested: the package does not export it, it is not documented, and nothing uses it.
- An invalid or missing `Content-Length` closes the connection, because the peer cannot find the start of the next message.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: adds requirements that notifications are never answered, that header names are matched case-insensitively, and for an invalid `Content-Length` and an unknown charset.

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py`: header parsing in the read loop, `handle_message`, the handling of notifications; removal of `JsonRpcEndpoint`.
- **Public API:** `jsonrpcpeer.peer.JsonRpcEndpoint` is removed; the package never exported it.
- **Interoperability:** peers that send header names in lower case now work.
- **Tests:** `tests/unit/test_peer.py`.
- **Order:** after `fix-peer-lifecycle` and `fix-rpc-error-responses`, which change the same file.
