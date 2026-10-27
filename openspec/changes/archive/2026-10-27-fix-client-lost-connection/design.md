# Design

## Context

See proposal.md for the motivation and specs/client/spec.md for the requirements. This change builds on the earlier changes of the series:

- `fix-peer-pending-requests`: When the connection closes, pending requests fail with `JsonRpcConnectionClosedError`, with the read error as `__cause__`.
- `fix-client-session-error-state`: `start_error` describes only a failed start, and `JsonRpcRemote` stores only started sessions.
- `fix-client-handshake-cleanup`: `close_connection()` records the exit code of a `stdio` server.
- `fix-client-stranded-calls`: keyword calls go through `_Session.submit()`, the `ended` event marks the end of the worker, and the worker thread does not raise.

Today, nothing distinguishes "the client closed the session" from "the connection went away":

- `_Session.stop()` and the end of the connection both leave the session without peer and loop.
- `JsonRpcRemote._start_session()` keeps returning the stored session.

## Goals / Non-Goals

**Goals:**

- A loss is recognized at the start of the next call, with a stable message that names the cause.
- A keyword running at the moment of the loss is reported as such and never resent.
- A client-side close is never mistaken for a loss.

**Non-Goals:**

- Reconnecting: `add-client-connect-retry`, opt-in.
- Half-open connections without FIN/RST: they are not detectable without a per-call timeout (backlog CLIENT-1).
- A server that keeps the connection open while it shuts down: `fix-server-shutdown-with-clients`.

## Decisions

### 1. `closed_by_client` is set first in `_Session.stop()`

`stop()` sets the flag before it starts the teardown. Any end of the connection that happens after that is a client-side close.

- **Alternative:** infer the intent from the teardown path. That is fragile, because the read loop ends the same way in both cases.

### 2. Loss = started, not closed by the client, and the connection handling has ended

A session counts as lost when all three hold:

- its handshake completed (it has a library token);
- `closed_by_client` is not set;
- either its read loop has ended (the peer is gone or no longer running) or its worker has ended (`ended`).

Checking the read loop detects the loss as soon as EOF is processed, not only after the cleanup. This state is read from the Robot thread; plain attribute reads are atomic.

### 3. The worker records the cause; the message waits for the worker to finish

- **Recording the cause:** When waiting on `peer.completion` ends with an exception, the worker stores it as the connection error. A clean completion stores nothing.
- **Building the message:** A helper composes the cause. It first waits for `ended`, bounded by `rpc_timeout`, so that a `stdio` exit code recorded by `close_connection()` is available. Its result:
  - "the connection was closed by the server" without an error;
  - otherwise `"<ErrorType>: <message>"`;
  - plus " (server process exited with code N)" when an exit code is known.

### 4. `_start_session()` raises for a lost session and keeps it until the scope ends

If the stored session is lost, `_start_session()` raises `ConnectionError(f"Connection to '{uri}' was lost: {cause}")`. The session stays stored, so every call fails the same way and none opens a connection.

`_stop_session()`, called at the end of `rpc_scope` through the listener, clears it, and the next call starts a new session through `_connect()`.

- **Alternative:** drop the dead session, so the next call connects again. That is an implicit reconnect that silently re-imports the remote library. It was explicitly rejected; reconnecting is opt-in in `add-client-connect-retry`.

### 5. `run_keyword` maps transport failures of a lost session

`run_keyword` catches `ConnectionError` around the submitted call. That covers `JsonRpcConnectionClosedError` from the peer and the "is closed" error from `submit()`. It also catches `CancelledError`.

- **Session lost:** It raises `ConnectionError(f"Connection to '{uri}' was lost while running keyword '{name}': {cause}")` from the original error.
- **Session healthy:** It re-raises the original unchanged. A `CancelledError` then means Robot cancelled the keyword, for example on a timeout, and must propagate.

The call is never sent again.

### 6. README section "Lost connections"

The section describes the behavior and the messages. `add-client-connect-retry` adds the opt-in later.

### 7. Test helpers, written from scratch

- **`Kill Jsonrpc Server`:** a keyword in `tests/robot/ServerControl.py`. It kills the isolated server, waits for it and records the exit code, simulating a crash or container restart.
- **Probe library:** loaded on the server, it never writes to stdout, so it also works over `stdio`. It offers `Echo` and `Exit Server`. `Exit Server` appends a line to a record file in the temp directory, passed by name rather than path to avoid escaping problems on Windows, and then ends the server process with a given exit code while the call is running.
- **Suites:** The TCP suite uses its own port, 8275. The `stdio` suite is tagged `posix`.

## Risks / Trade-offs

- **[A call right after the server died can still be sent]** The client notices EOF a moment after the server dies. A call made in that window goes out on the dead connection and fails as "lost while running keyword". The outcome is correct (failed, not resent), only the message differs. → The suites end the server *during* a call, or wait briefly after killing it, so they are deterministic.
- **[Waiting for the worker before building the message]** The wait is bounded by `rpc_timeout` and normally instant, since the cleanup of a lost connection is fast.
- **[Server keeps connections open while it shuts down]** On Python ≥ 3.12.1 a stopping server keeps the connection open, and the loss is only seen at SIGKILL. → `fix-server-shutdown-with-clients`.
