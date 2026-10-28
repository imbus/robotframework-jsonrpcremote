# Proposal

## Why

Every `JsonRpcPeer` stays in memory until the process ends. Its constructor calls `weakref.finalize(self, self._on_finalize)`. The bound method holds a strong reference to the peer, so the finalizer registry keeps the peer alive, and with it the reader, the writer, the transport and the endpoint with the handlers. The Python documentation of `weakref.finalize` warns against exactly this. The finalizer is useless anyway: while the peer is running, its read task keeps it alive.

On the server this leaks about 10 KB per connection. With 1200 connections in a row (connect, import, stop) against a server hosting `JsonRpcRemote.Echo`, its RSS grew from 34.2 to 45.9 MiB; with the finalizer neutralized, from 34.5 to 36.8 MiB. Long-running servers are hit hardest, such as the sidecar from issue #2. The client leaks one peer per session, which is one per test with `rpc_scope=TEST`.

Two smaller lifecycle defects come with it:

- `stop()` on a peer that was never started waits forever, because it waits for the end of a read loop that never ran.
- The constructor creates an `asyncio.Future`, so creating a peer outside a running event loop fails on Python 3.14 and later (`RuntimeError: There is no current event loop`) and warns on 3.12 and 3.13.

Found in the project review of 2026-10-27 (items PEER-4 and PEER-6).

## What Changes

- **No more leak:** the peer no longer registers a finalizer that references it, so a peer that has ended can be garbage collected together with its connection objects.
- **`stop()` before `start()`:** returns at once.
- **Construction:** a peer can be created without a running event loop; it binds to the loop when it starts.
- **Tests:** a stopped peer, and a peer whose connection the remote side closed, are garbage collected; the leak measurement on the server is repeated before and after the fix.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: adds requirements that a peer that has ended can be garbage collected, that stopping a peer that was never started returns at once, and that a peer can be created outside a running event loop.

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py` (`JsonRpcPeer.__init__`, `start()`, `stop()`, `completion`, `_on_finalize`).
- **Public API:** unchanged; `completion` keeps its meaning.
- **Client and server:** no code change; both stop keeping one peer per connection or session alive.
- **Not in this change:** the `asyncio.get_event_loop()` calls in the client and in the server endpoint. They always run inside a running loop and return it.
- **Tests:** `tests/unit/test_peer.py`.
- **Order:** independent; it comes before `fix-peer-message-handling` and `fix-rpc-error-responses`, which change the same file.
