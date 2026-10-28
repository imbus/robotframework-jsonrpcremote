# Tasks

## 1. Server: argument defaults on every Robot Framework 7 release

- [x] 1.1 In `packages/server/src/robot_jsonrpcremote_server/_runner.py`, import `NOT_SET` from `robot.utils` instead of `NotSet`, and decide in `_robot_import_library` whether an argument has a default with `arg.default is NOT_SET` (design decision 1). Verify with a Robot test that calls a keyword of `tests/robot/ServerProbeLib.py` with an optional argument once with and once without that argument (add such a keyword if none exists), on the installed Robot Framework; the run on 7.0 follows in 4.1

## 2. Client: console messages on every Robot Framework version

- [x] 2.1 In `src/JsonRpcRemote/__init__.py`, detect once at import whether `logger.write` accepts `console`, and route every forwarded message through one helper: with `console` where it is supported, otherwise `logger.write(message, level, html)` followed by `logger.console(message)` for a message marked for the console (design decision 2). Verify with unit tests in a new `tests/unit/test_client_logging.py` that patch the detection result and use a stand-in `logger.write` without a `console` parameter: the message is written with its level and HTML flag, a console message also reaches `logger.console` exactly once, and a message not marked for the console does not

## 3. Client: log messages outside a keyword call

- [x] 3.1 Add the log sink with submit, attach, detach and drain under one lock, owned by `JsonRpcRemote` and passed through `_Session` to `_ClientEndpoint`. `_log_notification` only submits to it, and `run_keyword` attaches Robot Framework's loop where it set `callback_loop` and detaches it in `finally` (design decision 3). Verify with unit tests of the sink:
  - messages submitted while detached are written in arrival order when the loop is attached, before any message submitted while attached;
  - a drain writes the queued messages on the calling thread;
  - a drain does not raise when a write raises
- [x] 3.2 Drain the sink in the `finally` of `_start_session()` and `_stop_session()` (design decision 4). Extend `tests/unit/fake_server.py` so that a scripted answer can first send log notifications to the client, for example before it answers `importLibrary` or `finalizeLibrary`. Verify with fake-server tests that the messages reach `logger.write` on the main thread, in the order sent:
  - messages sent during the import are written once `JsonRpcRemote(...)` returns;
  - the messages of a failed import are written before the import error is raised;
  - messages sent while a session ends are written when `_stop_session()` returns;
  - with `rpc_scope=TEST`, the messages of the re-import in the next test are written while that keyword call runs, before its result
- [x] 3.3 Add a Robot suite on its own server (next free port, 8278) that hosts a new test library with scope `SUITE` that is its own library listener and logs a warning in `_close`, which the server calls when it finalizes the library. The suite runs a small inner suite in a nested Robot process and reads the inner output file (design decision 5). Verify that it passes and that the warning from the finalization at the end of the inner suite's scope appears among the inner run's execution errors

## 4. Supported Robot Framework versions

- [x] 4.1 Run the unit tests and the Robot suites against the latest patch release of Robot Framework 7.0, 7.1, 7.2, 7.3, 7.4 and 7.5, each in its own virtual environment with the workspace packages and the dev dependencies the tests need, one version after another because of the fixed ports. Verify that all pass, including `Server Log Is Forwarded To The Client` on 7.1 to 7.3. If a version fails for a reason that is not as cheap to fix, raise the minimum to the oldest version that passes, as the proposal's first assumption states: `robotframework>=` in `pyproject.toml` and `packages/server/pyproject.toml`, the requirement in `README.md` and `packages/server/README.md`, and a note in proposal.md; then verify that the new minimum passes

## 5. Integration checks

- [x] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 5.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [x] 5.3 Commit code, tests, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`): subject `fix: require Robot Framework 7.2 and forward logs on 7.2 and 7.3` (no scope, since both packages change), a body that explains why 7.0 and 7.1 are dropped, the `console` parameter, `NOT_SET` and the log messages outside a keyword call, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`, which adds its requirements to `openspec/specs/client/spec.md` and `openspec/specs/server/spec.md`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-robot-framework-compatibility`, then run `uv run ruff format --check .`.
- macOS and Windows are only checked by CI after a push; the CI job for the minimum Robot Framework version follows in `add-ci-version-matrix`.
