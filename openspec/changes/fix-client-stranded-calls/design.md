# Design

## Context

See proposal.md for the motivation and specs/client/spec.md for the requirements. This change builds on `fix-client-session-error-state` (`start_error`, `_connect()`) and `fix-client-handshake-cleanup`.

In `src/JsonRpcRemote/__init__.py`:

- **How a keyword call crosses threads:** `JsonRpcRemote.run_keyword` hands the call to the session's loop with `asyncio.run_coroutine_threadsafe` and awaits the resulting `concurrent.futures.Future` via `asyncio.wrap_future`.
  - If the loop is about to stop when the call is scheduled, the scheduled callback may never run, and the future is never resolved.
  - If the loop has already closed, the call raises `RuntimeError: Event loop is closed`.
- **Repeated property access:** `run_keyword` reads the `_session` property four times, including once in its `finally`.
- **The worker thread body:** `_Session._run` is just `asyncio.run(self._run_client())`. A failed start re-raises inside the thread, and `threading.excepthook` prints it.
- **Teardown:** `_finalize_session`
  - suppresses errors only for the graceful shutdown;
  - lets errors from `peer.stop()` (`.result(timeout)`) escape;
  - returns early when `peer` or `loop` is `None`, which skips the `stdio` process backstop.
- **Where teardown runs:** in `stop()` (scope end via the listener), in `__del__`, and as the weakref finalizer at interpreter exit.

## Goals / Non-Goals

**Goals:**

- No call can wait forever on a session whose worker has ended.
- Teardown never raises and is bounded.
- No stderr output from the worker thread for errors that reach a caller anyway.

**Non-Goals:**

- Detecting a lost connection at the start of a call and naming its cause: `fix-client-lost-connection`.
- Cancelling a call that is running on a live session (Robot keyword timeouts keep the current behavior).

## Decisions

### 1. One submission point: `_Session.submit(coro)`

All coroutines that `JsonRpcRemote` runs on the session's loop go through `submit()`. Under a lock it:

1. checks that the loop is set and the session has not ended (a `threading.Event` named `ended`);
2. schedules the coroutine;
3. records the returned future in a set of outstanding calls.

If the session has ended, or the loop turns out to be closed (`RuntimeError` from scheduling), it closes the coroutine, so there is no "never awaited" warning, and raises `ConnectionError(f"Connection to '{uri}' is closed")`.

A done-callback removes the future from the set under the same lock.

- **Alternative:** check `loop.is_running()` before scheduling. That is racy, because the loop can stop right after the check, and it cannot fail calls that were already scheduled.

### 2. The worker fails stranded calls when it ends

`_run` wraps `asyncio.run(...)`. In its `finally`, it sets `ended` and takes the not-yet-done futures under the lock. Then, *outside* the lock, it fails them with `ConnectionError`; `InvalidStateError` from a race with completion is suppressed.

- **Why outside the lock:** Completing a future runs its done-callbacks, which take the same non-reentrant lock.
- **Why at that point:** Setting `ended` and draining under one lock means every call is either rejected by `submit()` or failed here. None slips through.

### 3. The worker thread does not let exceptions escape

`_run` catches `Exception` from `asyncio.run(...)` and logs it at debug level with a module logger (`logging.getLogger(__name__)`, with traceback). It does not re-raise.

The error is already where it belongs: `start_error` for a failed start, raised by `_connect()`, or the failing call. Since the thread runs outside Robot's main thread, Robot's logger is not used here.

- **Alternative:** keep printing via `threading.excepthook`. That is noise that duplicates the reported error, and with retries it would print once per attempt.

### 4. `run_keyword` uses one session reference and `submit()`

`JsonRpcRemote.run_keyword` reads `self._session` once into a local variable. It uses that reference for the callback loop, for `submit()` and in its `finally`. The `finally` therefore can no longer trigger a session start, and the call stays bound to the session it started on.

### 5. Teardown never raises and always cleans up

`_finalize_session`:

- runs every step (graceful shutdown, `peer.stop()`, thread join) under its own error suppression, bounded by `timeout`;
- always runs the `stdio` process backstop and clears the resources, also when `peer` or `loop` is already `None` (no early return before the backstop).

Because the weakref finalizer and `__del__` use the same function, interpreter exit and garbage collection are covered as well.

## Risks / Trade-offs

- **[Swallowed worker errors could hide a bug]** → They are logged at debug level with traceback through standard `logging`, and the error that matters still reaches the caller.
- **[Free-threaded Python]** The set of outstanding calls is only mutated or iterated under the lock, including in the done-callback, so this stays correct without the GIL.
- **[Message overlap with `fix-client-lost-connection`]** Calls on an ended session get a generic "Connection to '<uri>' is closed" here. → `fix-client-lost-connection` detects the loss before submitting and gives the specific message with the cause; the generic one remains for the shutdown race.
