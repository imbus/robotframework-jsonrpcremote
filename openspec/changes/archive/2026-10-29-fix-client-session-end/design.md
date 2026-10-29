# Design

## Context

See proposal.md for the motivation and specs/ for the requirements.

**How a session ends today** (`src/JsonRpcRemote/__init__.py`):

- `_Session.stop()` and the session's finalizer call `_finalize_session(resources, timeout)`, which only sees the `_SessionResources`, so that the finalizer does not keep the session alive.
- `_finalize_session()` passes the coroutines `endpoint.graceful_shutdown(timeout)` and `peer.stop()` to `_run_on_loop()`, which hands each to the worker's loop with `run_coroutine_threadsafe()` and waits up to `timeout` for it; then it joins the worker thread, again for up to `timeout`.
- The worker runs `asyncio.run(self._run_client())`. `_run_client()` awaits the peer's completion, calls `close_connection()`, and in its `finally` sets `resources.loop` to `None`. After that, `asyncio.run()` cancels the remaining tasks, shuts down async generators and the default executor, each by running the loop once more, and closes the loop. `_run()` then calls `_end()`, which sets `ended` and fails the calls the worker never ran.

**Why the end of a lost session stalls:** when the connection was lost, the worker is already finishing when the session ends. `_finalize_session()` may read the loop before `_run_client()` cleared it. A callback that `run_coroutine_threadsafe()` schedules after the loop's last run and before `close()` never runs: the client waits the full `timeout` per step, and the closed loop drops the never awaited coroutine. A callback that runs during one of the last runs starts a task that the closing loop destroys while pending.

**Who reads `rpc_scope`:** `JsonRpcRemote.__init__` stores it unconverted; `_end_test()` and `_end_suite()` compare it with `SessionScope.TEST` and `SessionScope.SUITE`. With the hint `SessionScope`, Robot Framework converts the import argument; for the hint `SessionScope | str` it passes a string through unconverted (checked with `TypeInfo.from_type_hint()` on Robot Framework 7.2 and 7.5).

## Goals / Non-Goals

**Goals:**

- Ending a session never waits for a worker that has ended, and never creates a coroutine on a loop that will not run it.
- A cancellation that does not belong to the worker never ends it early or reaches its thread.
- `rpc_scope` converts the same way from Python and from a `.robot` file.

**Non-Goals:**

- The total time ending a session may take while the server answers slowly. Each teardown step stays bounded by `rpc_timeout`, as the existing requirement says.
- Moving the teardown into the worker. See decision 1.

## Decisions

### 1. The teardown starts on the worker's loop, and only while the worker still runs its session

`_run_on_loop()` takes a function that creates the coroutine instead of the coroutine itself. It schedules a small starter with `loop.call_soon_threadsafe()`. The starter runs on the worker's loop: if `resources.loop` is no longer that loop, the worker has finished its session and there is nothing to tear down; otherwise it creates the coroutine and a task for it. Either way it reports back through a `threading.Event`. A closed loop makes `call_soon_threadsafe()` raise, and the call returns at once.

- The coroutine exists only once a running loop takes it, so nothing is left unawaited. A task the starter creates runs while `_run_client()` is still active; if the worker finishes before the task does, `asyncio.run()` cancels it with the other tasks instead of destroying it while pending.
- `resources.loop` is set and cleared on the worker's loop, so the starter reads it without a race.
- **Alternative:** move the teardown into the worker: ending a session only asks the worker to end, and the worker runs the graceful shutdown and closes the connection itself; the caller joins the thread. It removes cross-thread scheduling entirely, but rewrites the session's life cycle and the tests that drive `_finalize_session()` with fake loops. The starter fixes the race with a local change.

### 2. Waiting ends when the teardown is done or the worker has ended

`_SessionResources` gets the session's `ended` event, so that `_finalize_session()` can see it without referencing the session. `_run_on_loop()` waits for the starter's event in short slices of 50 milliseconds and stops early once `ended` is set, still bounded by `timeout`. When the worker has ended, its loop will run nothing more, so waiting longer cannot help.

- **Alternative:** let `_end()` complete the pending teardowns, as it fails the stranded calls. It needs a shared registry and a lock between `_finalize_session()` and the session. The slices cost at most 50 milliseconds of extra wait, and only when the worker ends during the teardown.

### 3. A cancellation from outside the session is told apart with `Task.cancelling()`

`close_connection()` catches `asyncio.CancelledError` around `writer.wait_closed()`. If the worker's own task is being cancelled, `asyncio.current_task().cancelling()` is greater than zero and the error goes on; otherwise the cancellation came from the shared close future, and the session carries on and reaps a stdio server. `_run()` catches `asyncio.CancelledError` next to `Exception` and logs it at debug level, as the last line of defense.

- **Alternative:** suppress `BaseException` in `close_connection()`. It would also swallow a real cancellation of the worker and `KeyboardInterrupt`.
- **Alternative:** only catch it in `_run()`. The thread would print nothing, but `close_connection()` would still skip reaping the stdio server.

### 4. `rpc_scope` is converted with Robot Framework's converter

`JsonRpcRemote.__init__` converts a string with `robot.api.TypeInfo.from_type_hint(SessionScope).convert(value, name="rpc_scope")`, which every supported Robot Framework version has (checked on 7.2 and 7.5). The hint becomes `SessionScope | str`.

- The rules and the error are Robot Framework's own: names match regardless of case, spaces and underscores, and an unknown name raises `ValueError: Argument 'rpc_scope' got value 'weekly' that cannot be converted to SessionScope: SessionScope does not have member 'weekly'. Available: 'GLOBAL', 'SUITE' and 'TEST'`.
- **Alternative:** convert with `SessionScope[value.upper()]`. Simpler, but it rejects spellings that a `.robot` file accepts today, such as `te st` or `TE_ST`, because Robot Framework passes the string through once the hint allows `str`.
- **Alternative:** keep the hint `SessionScope` and convert at runtime only. Type checkers would reject the string that the conversion accepts.

### 5. Unit tests drive the races deterministically; Robot tests cover what Robot Framework sees

- **Stall:** unit tests in `tests/test_client_session.py` with the existing fakes: a loop that is not closed and never runs again, with `ended` set, makes `_finalize_session()` return at once and leaves no coroutine unawaited; a loop that still runs but whose worker has finished its session makes the starter skip the teardown. The two tests that stalled run repeatedly on Python 3.14 and 3.15, where the race shows most.
- **Cancelled close:** a stdio session in `tests/test_client_connection.py` whose writer raises `CancelledError` from `wait_closed()` still records the server's exit code and prints no thread exception; a `CancelledError` raised from `close_connection()` itself checks `_run()` on its own.
- **`rpc_scope`:** unit tests with the fake server for a string scope in two spellings and an unknown name; a new Robot suite on port 8279 with a library that keeps a value per session and a subclass of `JsonRpcRemote` that passes `rpc_scope="TEST"`, and an `Import Library` with an unknown scope.
- No Robot test for the stall or the cancelled close: both depend on timing, and the cancelled close shows only on the console, not in Robot Framework's results.

## Risks / Trade-offs

- **[A teardown that the worker's finish cancels]** When the worker finishes while the graceful shutdown runs, `asyncio.run()` cancels it, and the server may not receive `exit`. → The connection is ending anyway; the server finalizes the library of a closed connection on its own.
- **[Polling while the worker ends]** The wait checks `ended` every 50 milliseconds. → Only while a teardown is pending; the normal case returns when the teardown is done.
- **[Robot Framework's converter changes its message]** The error text comes from Robot Framework. → The tests match the listed names, not the whole message.
