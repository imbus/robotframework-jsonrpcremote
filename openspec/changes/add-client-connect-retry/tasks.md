# Tasks

## 1. Options

- [x] 1.1 Add `_time_option(name, value)` and parse `rpc_timeout`, `rpc_connect_retry_timeout` (default `0`) and `rpc_connect_retry_interval` (default `1s`) in `JsonRpcRemote.__init__` before connecting, rejecting invalid or negative values and an interval of 0 or less while retry is enabled; assign `self.__session` before the validation (design decision 1). Verify with unit tests:
  - numbers, Robot time strings (`"60s"`, `"1 minute"`) and plain numeric strings are accepted;
  - `"soon"` and negative values fail with an error that names the option;
  - an interval of `0` with retry enabled fails;
  - the options do not appear in the library's forwarded init arguments
- [x] 1.2 Document the options in the README argument list and in the list of client options that are not forwarded, and note that `rpc_timeout` accepts time strings (design decision 7); verify the examples in the README use names and formats that the tests in 1.1 accept

## 2. Retry window and giving up

- [x] 2.1 Add `_connect_with_retry()` around `_connect()` with the "window spent" state, and use it for every new session in `_start_session()`, including the import (design decisions 2, 3); verify with fake-server tests:
  - with a window of 10s and the fake server starting after about 1s, the import succeeds after several attempts;
  - with a window of 1s and no server, the call fails after about 1s with a `ConnectionError` naming the URI, the window, the number of attempts and the last error;
  - the next call fails after one attempt without waiting;
  - once the server listens again, the next call succeeds, and a later outage waits the full window again
- [x] 2.2 Log an INFO message when a connection without a preceding loss needed more than one attempt (design decision 6); verify with a test that captures Robot's logger: no warning, one INFO message naming the attempts

## 3. Reconnect after a loss

- [x] 3.1 Capture the definition registered at import, turn a lost session into "pending loss" when retry is on, reconnect through the retry loop, and log the warning on success (design decisions 2, 4, 5); verify with fake-server tests:
  - after the fake server closed the connection and accepts again, the next call returns its result, and exactly one warning names the cause, the duration, the attempts and the reset of the server-side state;
  - with retry off, the behavior from `fix-client-lost-connection` is unchanged
- [x] 3.2 Add the definition check with the "incompatible" state (design decision 4); verify with fake-server tests: after the fake server comes back with one more keyword in its definition, the call fails with a `ConnectionError` stating that the library definition changed; further calls fail the same way without a new connection; after `_stop_session()`, the next call starts a new session
- [x] 3.3 Extend the README section "Lost connections" with the opt-in, giving up, the warning, the definition check and the reset of server-side state (design decision 7); verify it reads correctly and matches the messages asserted in the tests

## 4. End-to-end

- [x] 4.1 Add a `wait` option to `Start Jsonrpc Server` in `tests/robot/ServerControl.py` that returns without waiting for the port, to make calls while the server is still starting; verify through the suites in 4.2 and 4.3
- [x] 4.2 Add a TCP suite on port 8277 using `IsolatedServerControl.py` and the probe library from `fix-client-lost-connection`, and verify it passes on Linux, macOS and Windows. It covers:
  - a restart while idle reconnects, and the warning appears in the captured log;
  - a call made while the server is still starting waits and succeeds;
  - `Exit Server` during a call fails that call, and the record file holds exactly one line;
  - giving up after a short window, followed by a fast single attempt, then recovery once the server is back;
  - several restarts in one session
- [x] 4.3 Add a `stdio` suite tagged `posix`: `Exit Server` with exit code 3 fails that call, the next call starts a new server process and returns its result, and the warning names exit code 3; verify it passes on Linux and macOS

## 5. Integration checks

- [x] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 5.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [x] 5.3 Commit code, tests, README and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `feat(client): add opt-in connect retry`, a body that explains the options and the behavior, `Closes #2`, and the trailer `Co-authored-by: Fabian Tsirogiannis <fabian.tsirogiannis@imbus.de>`; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive` only after `fix-client-lost-connection` is archived; the `MODIFIED` requirement needs the existing `client` spec, and archive refuses it before then.
- Commit the archive as its own signed commit: `docs(openspec): archive add-client-connect-retry`.
- Close PR #3 with a comment that links the commits of all changes in this series.
