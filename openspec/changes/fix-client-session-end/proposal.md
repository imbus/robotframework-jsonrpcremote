# Proposal

## Why

Ending a session can block Robot Framework for the full `rpc_timeout`, 10 seconds by default. `_finalize_session()` schedules the graceful shutdown and `peer.stop()` on the session's event loop with `run_coroutine_threadsafe()`. If that loop has already stopped but is not closed yet, which happens while the worker thread's `asyncio.run()` finishes, the scheduling succeeds but the coroutine never runs. The client then waits for the full timeout, and Python reports `coroutine 'JsonRpcPeer.stop' was never awaited`. This hits the end of a lost session at the end of its `rpc_scope`, and the replacement of a lost session when connect retry reconnects.

It shows on Python 3.13 and later: there, `test_call_after_the_lost_session_ended_connects_again` stalls for exactly its `rpc_timeout` of 5 seconds in about one of three runs, always together with that warning, and never on 3.10 or 3.12. That is why the unit tests often take about 14 instead of 9 seconds on 3.13 and later.

A second defect affects when a session ends at all: `rpc_scope` given as a string from Python, for example `JsonRpcRemote(uri, rpc_scope="TEST")` in a Python library, never equals the `SessionScope` members the client compares it with, so the session does not end with its scope. Robot Framework's argument conversion hides this for imports in `.robot` files.

Found in the project review of 2026-10-27 (items CLIENT-5 and CLIENT-3).

## What Changes

- **Session end:** ending a session no longer waits on a coroutine that its event loop will not run. The client stops waiting as soon as the session's worker has ended, and it creates the coroutine only on the loop that runs it, so none is reported as never awaited.
- **`rpc_scope`:** accepts the scope names as strings from Python, the way Robot Framework's argument conversion accepts them. An unknown name fails the import with an error that lists the valid names.
- **Tests:** ending a lost session returns well within `rpc_timeout`, also while its worker is just finishing, checked repeatedly on Python 3.13 or later; a session with `rpc_scope="TEST"` from Python ends with the test.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: adds requirements that ending a session whose worker has ended does not wait for `rpc_timeout`, and that `rpc_scope` accepts the scope names as strings.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py` (`_run_on_loop()`, `_finalize_session()`, the handling of `rpc_scope` in `JsonRpcRemote.__init__`).
- **API:** the type hint of `rpc_scope` also allows a string.
- **Behavior:** a session that is lost or replaced ends without the stall; otherwise unchanged.
- **Tests:** unit tests with the fake server in `tests/unit/test_client_session.py`.
- **Order:** before `add-ci-version-matrix`, so the new jobs on Python 3.13 and later do not inherit the stall.
