# Tasks

## 1. Detect and report a lost connection

- [x] 1.1 Set `closed_by_client` at the start of `_Session.stop()`, add the loss state (started, not closed by the client, read loop or worker ended), let the worker record the error that ended the connection, and add the helper that builds the cause, waiting for `ended` bounded by `rpc_timeout` (design decisions 1–3); verify with fake-server unit tests: after the fake server closes the connection, the session counts as lost and the cause is "the connection was closed by the server"; after the fake server resets it, the cause names `ConnectionResetError`; after `stop()`, the session does not count as lost
- [x] 1.2 Make `_start_session()` raise `ConnectionError("Connection to '<uri>' was lost: <cause>")` for a lost session and keep the session stored until `_stop_session()` (design decision 4); verify with fake-server tests: two calls after a loss both fail with that message and the fake server sees no new connection; after `_stop_session()` the next call opens a new connection and returns its result
- [x] 1.3 Make `run_keyword` map a `ConnectionError` or `CancelledError` of a lost session to `ConnectionError("Connection to '<uri>' was lost while running keyword '<name>': <cause>")` and re-raise everything else unchanged (design decision 5); verify with fake-server tests: the fake server closes the connection while a `robot/run_keyword` request is pending (scripted never to answer), the call fails with that message, and the fake server received the request exactly once; a `CancelledError` on a healthy session still propagates
- [x] 1.4 Add the README section "Lost connections" describing detection, the messages, the running-keyword case and the end of the session by `rpc_scope` (design decision 6); verify the section reads correctly in the rendered README and its examples match the messages asserted in the tests

## 2. End-to-end

- [x] 2.1 Add the test helpers (design decision 7): a `Kill Jsonrpc Server` keyword in `tests/robot/ServerControl.py`, and a probe library in `tests/robot/` with `Echo` and `Exit Server`; `Exit Server` appends to a record file named in the temp directory and ends the server process with a given exit code, never writing to stdout. Also add a `stdio` server command for the probe library to `tests/robot/stdio_vars.py`; verify the helpers through the suites in 2.2 and 2.3
- [x] 2.2 Add a TCP suite on port 8275 using `IsolatedServerControl.py` and verify it passes on Linux, macOS and Windows. It covers:
  - idle loss: kill the server and wait briefly; the next call fails with `ConnectionError: Connection to 'tcp://127.0.0.1:8275' was lost: *`, and a second call fails the same way;
  - running keyword: `Exit Server` fails with `*lost while running keyword 'Exit Server'*`, and the record file holds exactly one line;
  - new session: after the server is restarted, the next test (`rpc_scope=TEST`) gets the result of its call
- [x] 2.3 Add a `stdio` suite tagged `posix`, in which `Exit Server` with exit code 3 fails with a message containing `server process exited with code 3`, and the next call in the same session fails with the lost-connection message; verify it passes on Linux and macOS and is excluded on Windows by the `robot.toml` profiles

## 3. Integration checks

- [x] 3.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 3.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [x] 3.3 Commit code, tests, README and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `fix(client): report a lost connection clearly`, a body that explains the behavior, `Refs #2`, and the trailer `Co-authored-by: Fabian Tsirogiannis <fabian.tsirogiannis@imbus.de>`; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive` after `fix-client-stranded-calls` is archived.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-client-lost-connection`.
