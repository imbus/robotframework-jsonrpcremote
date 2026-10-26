# Tasks

## 1. Fake JSON-RPC server for client tests

- [ ] 1.1 Add a typed test helper module in `tests/unit/` (not collected by pytest) that runs a fake server on its own thread and event loop (design decision 6): built on `JsonRpcPeer`; answers `robot/initialize`, `robot/initialized`, `robot/import_library`, `robot/run_keyword`, `robot/finalize_library`, `robot/shutdown` and `robot/exit`; scriptable per method to answer, fail with a JSON-RPC error, or never answer; counts accepted connections and records when each one closes; can be stopped and started again on the same port. Verify with a smoke test in which `JsonRpcRemote` imports a library from the fake server and runs a keyword, and with `uv run mypy` passing for the module

## 2. Error state describes only the session start

- [ ] 2.1 Rename `_Session.last_error` to `start_error` and write it only when connecting or the handshake fails in `_run_client`; remove the writes in `_Session.run_keyword` and on the end of the connection (design decisions 1, 2); update `tests/unit/test_client_connection.py`; verify the existing unit tests pass
- [ ] 2.2 Add tests against the fake server and verify they pass: a keyword call answered with a JSON-RPC error fails, and the next call in the same session returns its result; a keyword whose result carries a remote error fails, and the next call returns its result; `start_error` stays `None` in both cases

## 3. Keep only sessions that started

- [ ] 3.1 Add `JsonRpcRemote._connect()` and make `_start_session()` store only a session that started; remove the re-raise of a stored error for an existing session (design decisions 3, 5); verify with tests that end a healthy session via `_stop_session()` first: with the fake server stopped, the next call raises the connection error and no session is stored; once the fake server listens again, the next call returns its result; with `robot/import_library` scripted to fail, the call raises the server's error and the following call opens a new connection
- [ ] 3.2 On a start timeout, stop the session (errors from stopping suppressed) and raise `TimeoutError` chained from `start_error` (design decision 4); verify with a test in which the fake server never answers `robot/initialize`: with `rpc_timeout=1` the call raises `TimeoutError`, the fake server sees that connection closed within a few seconds, and the next call opens a new connection

## 4. End-to-end

- [ ] 4.1 Add a Robot suite in `tests/robot/` that runs its own server on port 8274 via `IsolatedServerControl.py`: the first test imports `JsonRpcRemote` with `rpc_scope=TEST`, calls `Echo`, and stops the server at its end; the second test expects the first call to fail with `ConnectionRefusedError: *`, starts the server again, and gets the result of the next call; the suite teardown stops the server. Verify the suite passes with `uv run --all-packages robotcode run`

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 5.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [ ] 5.3 Commit code, tests and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `fix(client): stop re-raising stale session errors`, a body that explains both problems, `Refs #2`, and the trailer `Co-authored-by: Fabian Tsirogiannis <fabian.tsirogiannis@imbus.de>`; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`, which creates `openspec/specs/client/spec.md` and moves the change to `openspec/changes/archive/`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-client-session-error-state`.
