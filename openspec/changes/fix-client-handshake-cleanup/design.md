# Design

## Context

See proposal.md for the motivation and specs/client/spec.md for the requirement. This change builds on `fix-client-session-error-state`: `start_error` and `JsonRpcRemote._connect()`.

In `_Session._run_client`:

- `close_connection()` runs only in the `finally` of the *second* phase, after a successful start, while waiting on `peer.completion`.
- **What happens on a failed start:**
  1. The first phase records `start_error`.
  2. It sets `initialized`.
  3. It re-raises.
  4. The outer `finally` clears `_res.loop`, `_res.peer` and `_res.thread`, but not `_res.process`.
- **TCP:** The connection only closes because `asyncio.run` cancels the peer's read task at loop shutdown, and the read loop closes the writer.
- **stdio:** The spawned process is never awaited.
- **Weakref finalizer:** It cannot help either, because `_finalize_session` returns early when `peer` or `loop` is `None`.

`close_connection()` already does the right thing for both transports:
- It feeds EOF to the reader and closes the writer.
- For a spawned process it waits up to `rpc_timeout`, then terminates, waits again and finally kills.

## Goals / Non-Goals

**Goals:**

- "Start failed" reaches the caller only after the connection is closed and a spawned server has exited.
- The exit code of a spawned server is available after it was reaped.

**Non-Goals:**

- Cleanup after a start that *timed out*: `fix-client-session-error-state` stops such a session.
- Messages that use the exit code: `fix-client-lost-connection` and `add-client-connect-retry`.

## Decisions

### 1. Await `close_connection()` in the start-failure path, before `initialized` is set

- **Why before `initialized`:** Setting `initialized` is what lets the caller see the failure. Cleaning up first guarantees the spec's "released before reported". It also means a retry never starts a second `stdio` server while the old one is still running.
- **Alternative:** clean up after setting `initialized`. The caller could start the next attempt while the old process is still alive.
- **Alternative:** keep relying on loop teardown. That is implicit, and the process stays unreaped.

### 2. Reuse `close_connection()` unchanged in its escalation

It already handles a missing peer (connecting failed before the peer existed) and the wait/terminate/kill sequence. No second cleanup path is needed.

### 3. Record the exit code in `close_connection()`

When it releases a process, `close_connection()` stores `process.returncode` on the session (for example as `process_returncode`) before it clears `_res.process`. After a final `kill()` it waits briefly so that the code is known; it stays `None` only if even that fails.

Both cleanup paths go through `close_connection()`, the failed start (this change) and the end of an established session. The code is therefore recorded in both cases.

## Risks / Trade-offs

- **[Slow cleanup can turn the reported error into a timeout]** `JsonRpcRemote._connect()` waits for `initialized` for at most `rpc_timeout`. Take a `stdio:` server that rejects the handshake but does not exit on EOF: cleanup takes longer than `rpc_timeout`, the caller gets `TimeoutError`, and the real error is chained as its `__cause__`. → Rare (normal servers exit at once on EOF), and the real error stays visible. In return the cleanup is guaranteed.
- **[Longer failure path]** A failed start now waits for the cleanup before it is reported. → Normally milliseconds; bounded by the existing escalation.
