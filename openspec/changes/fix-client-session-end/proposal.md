# Proposal

## Why

Ending a session can block Robot Framework for the full `rpc_timeout`, 10 seconds by default. `_finalize_session()` schedules the graceful shutdown and `peer.stop()` on the session's event loop with `run_coroutine_threadsafe()`. If that loop has already stopped but is not closed yet, which happens while the worker thread's `asyncio.run()` finishes, the scheduling succeeds but the coroutine never runs. The client then waits for the full timeout, and Python reports `coroutine 'JsonRpcPeer.stop' was never awaited`, or `Task was destroyed but it is pending!` when the coroutine started just before the loop stopped. This hits the end of a lost session at the end of its `rpc_scope`, and the replacement of a lost session when connect retry reconnects.

How often it shows depends on timing and on the Python version. On 2026-10-29, after `fix-peer-lifecycle`, 15 runs each of `test_call_after_the_lost_session_ended_connects_again` and `test_call_after_a_lost_connection_reconnects_and_logs_a_warning` stalled for exactly their `rpc_timeout` of 5 seconds, always with that warning, in 4 runs on Python 3.14 and in 6 on 3.15. On 3.12 none of them stalled, but the same day 2 of 3 full runs of the unit tests did. That is why the unit tests often take about 14 instead of 9 seconds. Against a real server, one of 1200 sessions of the leak measurement for `fix-peer-lifecycle` stalled for the default 10 seconds.

A second defect affects when a session ends at all: `rpc_scope` given as a string from Python never equals the `SessionScope` members the client compares it with, so the session does not end with its scope. Robot Framework's argument conversion hides this for imports in `.robot` files. It hits a library that builds on the client, for example a subclass of `JsonRpcRemote` that Robot Framework imports and that passes `rpc_scope="TEST"` itself.

A third defect shows when waiting for the connection to close is cancelled from outside the session, as the peer did before `fix-peer-lifecycle`: `_Session.close_connection()` and `_Session._run()` handle only `Exception`, so the `CancelledError` skips the release of a stdio server process and ends the worker thread, which prints it. That breaks the client requirement that session errors are not printed by the worker thread. The peer no longer causes it, but the client should not depend on that.

Found in the project review of 2026-10-27 (items CLIENT-5 and CLIENT-3) and, for the client part of PEER-7, while testing `raise-python-minimum`.

## What Changes

- **Session end:** ending a session no longer waits on a coroutine that its event loop will not run. The client stops waiting as soon as the session's worker has ended. It creates the teardown coroutines only on the loop that runs them and only while the worker still runs its session, so none is reported as never awaited or destroyed while pending.
- **Closing the connection:** a cancellation of the wait for the connection to close that does not come from the session itself no longer ends the worker early: the session still releases a stdio server process. The worker thread also catches a `CancelledError` that ends its session, so none is printed.
- **`rpc_scope`:** accepts the scope names as strings from Python. The client converts them with Robot Framework's own converter, so case, spaces and underscores do not matter, as in a `.robot` file, and an unknown name fails the import with Robot Framework's error, which lists the valid names. The type hint becomes `SessionScope | str`; Robot Framework then passes strings through unconverted, so the client's conversion keeps imports in `.robot` files as they are.
- **Tests:**
  - unit tests: ending a session whose worker has ended or is just finishing returns well within `rpc_timeout` and leaves no coroutine behind; a cancelled close still releases the stdio server and prints nothing; `rpc_scope` given as a string;
  - the two tests that stalled, run repeatedly on Python 3.14 and 3.15 without a stall;
  - Robot tests: a library that subclasses `JsonRpcRemote` and passes `rpc_scope="TEST"` starts a new session in each test, and an unknown `rpc_scope` fails the import with the valid names;
  - no Robot test for the stall and the cancelled close: both depend on timing, and the cancelled close shows only on the console, not in Robot Framework's results.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: adds requirements that ending a session whose worker has ended or is ending does not wait for `rpc_timeout`, and that `rpc_scope` accepts the scope names as strings; extends the requirement that session errors are not printed by the worker thread to a close that is cancelled from outside the session.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py` (`_SessionResources`, `_run_on_loop()`, `_finalize_session()`, `_Session._run()`, `_Session.close_connection()`, the handling of `rpc_scope` in `JsonRpcRemote.__init__`).
- **API:** the type hint of `rpc_scope` is `SessionScope | str`, also in Libdoc.
- **Behavior:** a session that is lost or replaced ends without the stall; otherwise unchanged.
- **Tests:** unit tests in `tests/test_client_session.py` and `tests/test_client_connection.py`; a new Robot suite in `atests/` on port 8279 with a small library that keeps a value per session and a subclass of `JsonRpcRemote`; locally also on Python 3.14 and 3.15, because CI runs only 3.12 until `add-ci-version-matrix`.
- **Order:** before `add-ci-version-matrix`, so the new jobs on Python 3.13 and later do not inherit the stall.
