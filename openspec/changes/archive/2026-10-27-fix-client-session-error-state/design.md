# Design

## Context

See proposal.md for the motivation and specs/client/spec.md for the required behavior.

In `src/JsonRpcRemote/__init__.py`:

- **Who writes `_Session.last_error`:** three places.
  - `_run_client` when connecting or the handshake fails (the start path);
  - `_run_client` when the connection ends with an error;
  - `_Session.run_keyword` on every exception of a keyword request.
- **How `JsonRpcRemote._start_session` uses it:**
  - It stores a new session *before* knowing whether it started.
  - On a timeout it raises, but keeps the session.
  - For any stored session it re-raises `last_error` on every call.
- **Threading:** Each session runs its own event loop in a worker thread. `initialized` (a `threading.Event`) is set when the start attempt ends, successfully or not, and the calling thread blocks on it with `rpc_timeout`.
- **Teardown can raise:** `_finalize_session` can still raise (for example a `TimeoutError` from `peer.stop()`) until `fix-client-stranded-calls`.

## Goals / Non-Goals

**Goals:**

- The session error state means "why this session failed to start", nothing else.
- `JsonRpcRemote` only ever holds a session that started successfully.
- A timed-out start leaves no worker thread or connection behind, as far as the client can control it.

**Non-Goals:**

- Closing the connection and reaping a spawned stdio server after a start that failed with an error: `fix-client-handshake-cleanup`.
- Detecting and reporting a lost connection: `fix-client-lost-connection`.
- Retrying a failed start: `add-client-connect-retry`.

## Decisions

### 1. Rename `last_error` to `start_error`; only the start path writes it

- **Why:** The name states the meaning. The generic name is what invited storing every failure there.
- **Alternative:** keep the name and document it. That leaves the trap in place.

### 2. Drop the other two writes

- `_Session.run_keyword` lets exceptions propagate unchanged.
- An error that ends the connection is no longer stored. `fix-client-lost-connection` records the cause of a lost connection in its own state, for its own messages.

### 3. Only a started session is stored

A new `JsonRpcRemote._connect()` creates and starts a session and waits for `initialized`. It returns the session only if it started; otherwise it raises. `_start_session()` assigns `self.__session` only from a successful `_connect()`.

The re-raise of a stored error for an existing session is removed: a stored session always started successfully, so there is nothing to re-raise.

### 4. Stop a timed-out start before raising

On a timeout, `_connect()` stops the session and then raises `TimeoutError(...) from session.start_error`. What `stop()` does depends on how far the worker got:

- **Peer already exists:** `stop()` runs the existing teardown. The graceful shutdown is bounded by `rpc_timeout` and its errors are suppressed. Then comes `peer.stop()`, which since `fix-peer-pending-requests` fails the pending handshake request. The worker then records a start error and ends.
- **No peer yet (still connecting):** `stop()` returns at once, and the worker's own connect timeout ends it.

Errors raised by `stop()` itself are suppressed at this call site, because `_finalize_session` can still raise until `fix-client-stranded-calls`. For the caller, the `TimeoutError` is the relevant error.

- **Alternative:** keep the timed-out session (today). That leaks a thread and possibly a connection that finishes the handshake later and imports the library on the server.
- **Alternative:** stop it in a background thread to return faster. More moving parts for a bounded wait.

### 5. A start that failed with an error is not stopped explicitly

When `initialized` is set and `start_error` holds the error, the worker is already ending. It releases what `_run_client` releases today. `_connect()` raises `start_error` without calling `stop()`; at that moment `stop()` could race with the loop shutting down. Closing the connection and reaping a stdio server on this path is `fix-client-handshake-cleanup`.

### 6. Test infrastructure: an in-process fake JSON-RPC server

A test helper module in `tests/unit/`, not collected by pytest, provides a fake server:

- **Own thread and loop:** It runs on its own thread with its own event loop. The client blocks the calling thread while it waits for `initialized`, so the fake server cannot share the test's loop.
- **Built on `JsonRpcPeer`:** It answers the client's protocol methods.
- **Scriptable per method:** answer with a value, answer with a JSON-RPC error, or never answer.
- **Records connections:** the number of accepted connections, and whether each has closed.

- **Why:** The real server cannot be scripted to "never answer the handshake" or to return a JSON-RPC error for a keyword call, and a subprocess per test is slow. `fix-client-handshake-cleanup`, `fix-client-stranded-calls` and `fix-client-lost-connection` reuse the helper.
- **End-to-end coverage:** One Robot suite against the real server covers the main scenario (server down when a session starts, then back) end to end.

## Risks / Trade-offs

- **[Every call after a failed start makes its own attempt]** With an unreachable host, each call can take up to `rpc_timeout`, for example several remote keywords in a teardown. → Intended: the server may be back, and the old fast failure re-raised a stale error. `add-client-connect-retry` makes waiting explicit and configurable.
- **[A timed-out start takes longer to report]** Stopping can add up to about `rpc_timeout` when the server does not answer at all. → Bounded. The alternative leaks the session.
- **[Interim message after a lost connection]** Until `fix-client-lost-connection`, later calls fail with `RuntimeError: Event loop is not initialized yet` instead of a stored connection error. → Both changes belong to the same unreleased batch.
- **[Connect completing right after the timeout]** If the TCP connect succeeds in the few milliseconds between the client's timeout and the worker's own connect timeout, `stop()` finds no peer yet, and the worker could still finish the handshake. → Negligible window; not addressed here.
