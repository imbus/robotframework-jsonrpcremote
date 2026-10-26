# Proposal

## Why

When the connection of a `JsonRpcPeer` ends while requests are still waiting for a response, those requests are never resolved. The caller waits until something tears down the event loop and then fails with a `CancelledError`, or it waits forever. For the Robot Framework client, this means a keyword that is running when the server goes away (crash, container restart) ends with a `CancelledError` instead of a meaningful connection error. Fabian Tsirogiannis reported this in #2 and fixed it in PR #3.

This is the first of a series of changes that rework PR #3 into separate changes. The later client changes (clear lost-connection errors, connect retry) build on this peer behavior.

## What Changes

- Requests that are still waiting for a response when the peer's read loop ends fail with a new `JsonRpcConnectionClosedError` instead of staying unresolved. This covers every way the read loop can end: the remote side closes the connection, a transport or framing error, an oversized message, a local `stop()`.
- Requests sent after the read loop has ended fail immediately with `JsonRpcConnectionClosedError`, without writing anything to the transport.
- `JsonRpcConnectionClosedError` is a subclass of the built-in `ConnectionError` and is exported from the `jsonrpcpeer` package. When the read loop ended because of an error, that error is attached as the exception's `__cause__`.
- Unchanged: the wire protocol, notifications, and the responses the peer sends for incoming requests.
- Behavior change, not breaking: a request that previously never completed now raises. `request_timeout` keeps working as before.

## Capabilities

### New Capabilities

- `jsonrpc-peer`: Behavior of the asyncio JSON-RPC 2.0 peer in the `jsonrpcpeer` package: request/response lifecycle, framing, and connection handling. This change introduces it with the requirements for requests around a closed connection.

### Modified Capabilities

_None._

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py` (closed state, failing outstanding requests, rejecting new ones) and `packages/jsonrpcpeer/src/jsonrpcpeer/__init__.py` (export).
- **Public API:** new exception `jsonrpcpeer.JsonRpcConnectionClosedError`.
- **Client (`src/JsonRpcRemote`):** no code change. A keyword that is running when the connection drops now fails with `JsonRpcConnectionClosedError` instead of `CancelledError`. Until `fix-client-session-error-state` lands, the client keeps re-raising that stored error on later calls in the same session. The clear lost-connection message follows in `fix-client-lost-connection`.
- **Server (`packages/server`):** no behavior change, because the server never sends requests to the client.
- **Tests:** new unit tests in `tests/unit/test_peer.py`.
- **Docs:** error-handling section of `packages/jsonrpcpeer/README.md`.
