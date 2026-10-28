# Proposal

## Why

Every `JsonRpcPeer` stays in memory until the process ends. Its constructor calls `weakref.finalize(self, self._on_finalize)`. The bound method holds a strong reference to the peer, so the finalizer registry keeps the peer alive, and with it the reader, the writer, the transport and the endpoint with the handlers. The Python documentation of `weakref.finalize` warns against exactly this. The finalizer is useless anyway: while the peer is running, its read task keeps it alive.

On the server this leaks about 10 KB per connection. With 1200 connections in a row (connect, import, stop) against a server hosting `JsonRpcRemote.Echo`, its RSS grew from 34.2 to 45.9 MiB; with the finalizer neutralized, from 34.5 to 36.8 MiB. Long-running servers are hit hardest, such as the sidecar from issue #2. The client leaks one peer per session, which is one per test with `rpc_scope=TEST`.

Further lifecycle defects come with it:

- `stop()` on a peer that was never started waits forever, because it waits for the end of a read loop that never ran.
- The same happens when `stop()` follows `start()` before the read loop got to run once. Cancelling the read task at that point skips its cleanup, so the peer neither resolves `completion` nor fails waiting requests nor closes the writer.
- The constructor creates an `asyncio.Future`, so creating a peer outside a running event loop fails on Python 3.14 and later (`RuntimeError: There is no current event loop`) and warns on 3.12 and 3.13.

A probe against the current peer on 2026-10-28 confirmed each of these on Python 3.10, 3.12, 3.13, 3.14 and 3.15, within the version limits stated above. It also showed that removing the finalizer is enough for an ended peer to be garbage collected, with and without an attached endpoint.

Found in the project review of 2026-10-27 (items PEER-4 and PEER-6); the second item of the list was found while planning this change.

## What Changes

- **No more leak:** the peer no longer registers a finalizer that references it, so a peer that has ended can be garbage collected together with its connection objects.
- **`stop()` when the read loop never ran:** whether the peer was never started or is stopped right after `start()`, `stop()` returns at once and ends the peer as the end of its read loop does: the connection counts as closed, so waiting requests fail and new ones are rejected; `completion` resolves; with `auto_close`, the writer is closed.
- **Construction:** a peer can be created without a running event loop; it binds to the running loop when it is first used.
- **Documentation:** the `jsonrpcpeer` README describes the peer's lifecycle: creating, starting, stopping and `completion`.
- **Tests:** a stopped peer, and a peer whose connection the remote side closed, are garbage collected, and so are the server's peer of a closed connection and the client's peer of an ended session. The leak measurement on the server is repeated before and after the fix.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: adds requirements that a peer that has ended can be garbage collected, that stopping a peer whose read loop never ran returns at once and ends the peer, and that a peer can be created outside a running event loop.

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py` (`JsonRpcPeer.__init__`, `start()`, `stop()`, `completion`, the cleanup at the end of `io_loop`, `_on_finalize`).
- **Public API:** unchanged; `completion` keeps its meaning.
- **Client and server:** no code change; both stop keeping one peer per connection or session alive.
- **Not in this change:** the `asyncio.get_event_loop()` calls in the client and in the server endpoint. They always run inside a running loop and return it.
- **Docs:** `packages/jsonrpcpeer/README.md`.
- **Tests:** `tests/unit/test_peer.py`, plus one test each in `tests/unit/test_server_stdio.py` and `tests/unit/test_client_session.py`; locally also on Python 3.12 and 3.14, because CI runs only 3.10 until `add-ci-version-matrix`.
- **Order:** independent; it comes before `fix-peer-message-handling` and `fix-rpc-error-responses`, which change the same file.
