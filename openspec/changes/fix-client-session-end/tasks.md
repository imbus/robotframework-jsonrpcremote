# Tasks

## 1. Session end without the stall

- [ ] 1.1 Add the session's `ended` event to `_SessionResources`, set by `_Session` when it creates its resources, and let `_run_on_loop()` take a function that creates the coroutine. It schedules a starter with `loop.call_soon_threadsafe()` that creates the coroutine and its task on the worker's loop only while `resources.loop` is still that loop, and waits for the starter's `threading.Event` in slices of 50 milliseconds until it is set, `ended` is set, or `timeout` has passed (design decisions 1 and 2). `_finalize_session()` passes `endpoint.graceful_shutdown` and `peer.stop` as functions. Verify with new unit tests in `tests/test_client_session.py`, built on `_resources()` and `_no_coroutine_left_unawaited()`, and run each against the code without the part it covers:
  - a loop that is not closed and does not run, with `ended` set: `_finalize_session(resources, 5)` returns within one second and leaves no coroutine unawaited; it fails without the check of `ended`;
  - a loop that runs in a thread while `resources.loop` is already `None`, as when the worker has finished its session: the teardown functions are never called and `_finalize_session()` returns within one second; it fails without the starter's check of `resources.loop`;
  - the existing tests for an unresponsive worker and a closed loop still pass
- [ ] 1.2 Run `test_call_after_the_lost_session_ended_connects_again` and `test_call_after_a_lost_connection_reconnects_and_logs_a_warning` 15 times each on Python 3.14 and 3.15, in environments outside the repository (`UV_PROJECT_ENVIRONMENT=<dir>/venv-<version> uv sync --frozen --all-extras --all-packages --dev --python <version>`, then `<venv>/bin/python -m pytest -rw --durations=0 --durations-min=3`). Verify that no run has a call over 3 seconds or reports a coroutine never awaited or a task destroyed while pending, against 4 of 15 runs on 3.14 and 6 of 15 on 3.15 before the change

## 2. A cancelled close does not end the worker

- [ ] 2.1 In `_Session.close_connection()`, catch `asyncio.CancelledError` from `writer.wait_closed()` and re-raise it only when `asyncio.current_task().cancelling()` is greater than zero; in `_Session._run()`, catch `asyncio.CancelledError` next to `Exception` and log it at debug level (design decision 3). Verify with new unit tests, and run each against the code without the part it covers:
  - in `tests/test_client_connection.py`, a stdio session whose peer's writer raises `asyncio.CancelledError` from `wait_closed()`: after `stop()`, `session.process_returncode` is set and `threading.excepthook` received nothing; it fails without the catch in `close_connection()`;
  - in `tests/test_client_session.py`, a session whose `close_connection()` raises `asyncio.CancelledError`, run as in `test_failed_start_is_not_an_unhandled_thread_exception`: the worker ends, `threading.excepthook` received nothing and the error is logged at debug level; it fails without the catch in `_run()`

## 3. `rpc_scope` as a string

- [ ] 3.1 In `JsonRpcRemote.__init__`, convert a string `rpc_scope` with `robot.api.TypeInfo.from_type_hint(SessionScope).convert(value, name="rpc_scope")` and change the hint to `SessionScope | str` (design decision 4). Verify with new unit tests in `tests/test_client_session.py` with the fake server, run against the code without the conversion:
  - `rpc_scope="TEST"` and `rpc_scope=" te st "` from Python end the session in `_end_test()`;
  - `rpc_scope="weekly"` raises `ValueError` naming `GLOBAL`, `SUITE` and `TEST`
- [ ] 3.2 Add the Robot suite `atests/rpc_scope.robot` on its own server on port 8279, with a library `atests/SessionValueLib.py` on the server that keeps a value per library instance (`Remember Value`, `Recalled Value`) and a client library `atests/TestScopedRemote.py` that subclasses `JsonRpcRemote` and passes `rpc_scope="TEST"` as a string. Verify that:
  - a value remembered in one test is gone in the next one, because each test runs in a session of its own; it fails without the conversion of 3.1;
  - `Import Library    JsonRpcRemote    ${URI}    SessionValueLib    rpc_scope=weekly` fails with an error that lists `'GLOBAL', 'SUITE' and 'TEST'`; it fails when the hint allows `str` but the conversion is missing

## 4. Integration checks

- [ ] 4.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 4.2 Run the unit tests on Python 3.14 and 3.15 in the environments from 1.2; verify all pass
- [ ] 4.3 Run `uv run --all-packages robotcode run`; verify all Robot suites pass, including `atests/rpc_scope.robot`. The stall and the cancelled close get no Robot test: both depend on timing, and the cancelled close shows only on the console, not in Robot Framework's results; the unit tests of 1.1, 1.2 and 2.1 cover them
- [ ] 4.4 Commit code, tests, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`): subject `fix(client): end sessions without stalling and accept rpc_scope names`, a body that explains the stall with the numbers from 1.2, the cancelled close, and the conversion of `rpc_scope`, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`, which adds and changes its requirements in `openspec/specs/client/spec.md`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-client-session-end`, then run `uv run ruff format --check .`.
- Set CLIENT-5, CLIENT-3 and the client part of PEER-7 to done in `playground/anforderungen-und-ideen.md`.
