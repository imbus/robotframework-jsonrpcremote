# Design

## Context

See proposal.md for the motivation and specs/jsonrpc-peer/spec.md for the required behavior.

In `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py`:

- **Registering requests:** `send_request_typed` registers a future in `_pending_requests` (id to future) *before* it writes the request. Only `_handle_response` resolves that future, and it runs for messages read by `io_loop`.
- **How the read loop ends:** `io_loop` is the only reader, and every way it can end passes through its `finally` block:
  - clean EOF (an `IncompleteReadError` without partial data at EOF), with `completion` set to `True`;
  - read or framing errors, stored on `completion`;
  - an oversized incoming message, via `running = False; return` without an exception;
  - cancellation by `stop()` or the weakref finalizer, re-raised and not stored.
- **The gap:** Nothing in that `finally` block touches `_pending_requests` today. Waiters stay pending until the event loop is torn down and cancels them.
- **Threading:** All peer state lives on a single asyncio event loop. Code between two `await`s runs without interleaving.

## Goals / Non-Goals

**Goals:**

- One place defines when the connection counts as closed, and the transition is atomic with respect to other coroutines on the loop.
- Every request is either rejected up front or failed by the closure. No request falls between the two.
- No "Future exception was never retrieved" noise caused by the new failures.

**Non-Goals:**

- Notifications and responses written after the close. Nothing waits on them, so they cannot hang; their behavior stays unchanged.
- Peers that were never started. Without a read loop there is no closure, and their behavior stays unchanged.
- Client-side handling: messages and session state are covered by `fix-client-session-error-state` and `fix-client-lost-connection`.
- A cancellation protocol for in-flight requests (backlog PEER-1).

## Decisions

### 1. The closure happens in the `finally` block of the read loop

The peer marks itself closed and fails outstanding requests at the end of `io_loop`, not in `stop()` or the individual exit paths.

- **Why:** Every termination path converges there, including the easily missed size-limit path. It is also exactly the moment after which no response can arrive anymore.
- **Alternative:** hooks in `stop()` and in each exit path. That duplicates the logic, and a new exit path would silently reintroduce the hang.
- **Alternative:** deriving "closed" from `completion.done()`. An explicit flag reads clearer at the call sites and does not tie request handling to the completion future.

### 2. Mark closed and fail requests in one synchronous step

In the `finally` block, in this order and before any `await`:

1. Set the closed flag.
2. Take and clear the pending map.
3. Fail every pending future that is not done yet.
4. Set `completion`.

The existing `writer.close()` / `await writer.wait_closed()` follows afterwards.

- **Why:** Without an `await` in between, no coroutine can register a request after the flag check but before the map is drained. A request either sees the flag (decision 4) or is in the map and gets failed.

### 3. Error type: `JsonRpcConnectionClosedError(ConnectionError)`

The exception is defined in `peer.py` next to the other peer exceptions and re-exported from `jsonrpcpeer/__init__.py` in the existing `from .peer import X as X` style (mypy runs with `implicit_reexport = false`). Messages:

- for outstanding requests: "Connection closed before a response was received";
- for rejected requests: the method name, e.g. "Cannot send request 'robot/run_keyword': the connection is closed".

- **Why `ConnectionError` as the base:** Callers can handle every transport failure in one `except ConnectionError`. `ConnectionResetError` and `BrokenPipeError` already derive from it.
- **Alternative:** the plain `ConnectionError`. It cannot be told apart from OS-level errors.
- **Alternative:** a JSON-RPC base exception. None exists; `JsonRpcInvalidRequestError` derives from `Exception`.

### 4. New requests are rejected up front

`send_request_typed` checks the closed flag first, before allocating an id, creating a future or writing anything. `send_request` delegates to it, so it is covered as well. Notifications are not guarded (see Non-Goals).

### 5. The cause is the error that ended the read loop; each request gets its own exception

The read loop remembers the exception it records on `completion` (read or framing errors, including an `IncompleteReadError` with partial data). The closure creates a separate `JsonRpcConnectionClosedError` for each pending request and sets that remembered exception as its `__cause__`.

- **No cause in these cases:** clean EOF, the size-limit path (it has no exception object) and cancellation by `stop()`. A `CancelledError` is not an error cause.
- **Why one instance per request:** A shared instance would share its traceback across unrelated waiters. The cause, in turn, is what `fix-client-lost-connection` needs for its "lost: <cause>" message.

### 6. Race between sending and closing

`_send_message` can await (`drain()`). If the read loop ends during that await, the closure fails the request's future, and the write then typically fails too, with an error such as `ConnectionResetError`. Today the caller would get that write error, and the failed future would never be retrieved. asyncio then logs "Future exception was never retrieved" when it is collected.

Fix: if writing raises and the request's future has already been failed by the closure, `send_request_typed` raises that future's `JsonRpcConnectionClosedError`. Reading the exception also marks it as retrieved. If the future is not failed, the write error propagates unchanged, for example the existing `ValueError` for oversized outgoing messages.

- **Alternative:** only mark the future's exception as retrieved and pass the write error on. Simpler, but depending on timing the caller would see different exception types for the same event.

### 7. Documentation

The "Error Handling" section of `packages/jsonrpcpeer/README.md` gets a short paragraph: outstanding and new requests fail with `JsonRpcConnectionClosedError` once the connection closes.

## Risks / Trade-offs

- **[Behavior change for callers]** A caller that relied on requests hanging until cancellation now gets an exception. → The only caller in this repository is the client, which already catches `Exception` there. The README documents the new behavior.
- **[Temporary client behavior]** Until `fix-client-session-error-state` lands, the client stores the connection-closed error as `last_error` and re-raises it on later calls in the same session. → Accepted for one change. That fix is next in line.
- **[Remaining race]** If the write fails *before* the read loop notices the EOF, the caller still gets the plain write error. By the definition in the spec, the connection was not yet closed at that point. → It is still a `ConnectionError` in practice. Requests sent afterwards are rejected by the closed flag.
