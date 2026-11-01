# Tasks

Every new test is run once against the code without the part of the change it covers, and must fail there.

## 1. Protocol

- [ ] 1.1 In `robot_jsonrpcremote_protocol`, add the optional field `log_level: str | None` to `InitializeParams`, the dataclass `SetLogLevelParams(log_level: str)` and the method `SET_LOG_LEVEL_NOTIFICATION = "robot/set_log_level"` (design decision 4). Verify with a test in `tests/test_protocol.py` that both parameter types round-trip through `as_dict` and `from_dict` and that the method name is `robot/set_log_level`. No Robot test: the definitions alone change nothing that Robot Framework shows; tasks 3.1 and 5.1 use them

## 2. Server: failures

- [ ] 2.1 In `_runner.py`, add a function that builds a `RunKeywordError` from Robot's `ExecutionFailed`: the message of the failure; the type and the traceback of its `__context__`, formatted with Robot's `ErrorDetails`; and the mode `SKIP`, else `FATAL`, else `CONTINUABLE`, else none (design decision 1). `_robot_run_keyword` raises a server exception that carries this error. Verify with unit tests in `tests/test_runner.py` on real `HandlerExecutionFailed` errors raised while handling `ValueError("bad value")`, `AssertionError("boom")`, `SkipExecution`, `ContinuableFailure` and `FatalError`. They cover the server scenarios:
  - Keyword raises a ValueError;
  - Keyword fails an assertion;
  - Type and traceback of a failure;
  - Skip, Continuable failure, Fatal failure and Normal failure.
- [ ] 2.2 In `_endpoint.py`, `run_keyword` answers the server exception of 2.1 with its error and logs the failure at DEBUG; every other exception keeps `logger.exception` and the message alone (design decisions 1 and 2). Verify with tests in `tests/test_endpoint.py` with the stub context:
  - a failure gives the full `RunKeywordError` and a DEBUG record without an ERROR record;
  - another exception gives only its message and an ERROR record.

## 3. Server: log levels

- [ ] 3.1 The endpoint keeps the log level that its client reports in `robot/initialize` and in `robot/set_log_level`, INFO if there is none. Before it runs a command, the runner sets Robot's log level with `set_log_level` to the level of the command's subscriber, INFO without one (design decision 4). Verify with tests in `tests/test_endpoint.py` (level from `robot/initialize`, from the notification, INFO by default) and in `tests/test_runner.py` (a command runs at the level of its subscriber, one without a subscriber at INFO). The real server over the protocol, without the client, shows what the client cannot, because it drops messages below its level itself: `tests/test_server_end_to_end.py` covers the server scenarios Client at DEBUG, Client changes its log level and Client without a log level, a second client at another level, Python's `logging`, and the fields of a failure and a call after a fatal failure. The Robot test follows in 5.2, once the client reports its level
- [ ] 3.2 The runner does not forward the DEBUG message with the traceback that Robot logs right after the FAIL or SKIP message of a failure, since the client logs the traceback from the error (design decision 4). Verify with tests in `tests/test_runner.py` (not forwarded after FAIL and SKIP; the first DEBUG message of the next command is forwarded), in `tests/test_server_end_to_end.py` (the scenario Traceback of a failure) and with the Robot test of 4.2, which expects the traceback once
- [ ] 3.3 `configure_logging` gives the handler that prints to stderr the server's own level, so the log level of a client does not change what the server prints (design decision 4). Verify with a test in `tests/test_server_cli.py` that runs in its own process, for the scenario Library logs for a client at DEBUG

## 4. Client: failures, with their Robot tests and documentation

- [ ] 4.1 In `JsonRpcRemote.run_keyword`, raise `robot.errors.RemoteError(message, traceback or "", fatal=…, continuable=…)` and set `ROBOT_SKIP_EXECUTION` for `SKIP` (design decision 3). Verify with tests in `tests/test_client_failures.py` on the fake server, which scripts a `RunKeywordResult` with an error for each mode, with a traceback and with a message only. The tests check:
  - the message;
  - `details` and the three attributes;
  - that a message-only failure sets no attribute.

  They cover the client scenarios Remote keyword raises a ValueError, Remote keyword fails an assertion and Server reports only a message.
- [ ] 4.2 Robot tests for the failure modes (design decision 6):
  - **`atests/NestedRobot.py`:** `Run Nested Suite` gets the options `log_level` and `allow_failures`, and new keywords return the status and message of each test and the messages of a test at a level.
  - **The new suite `atests/failure_modes.robot`** starts its own server on port 8280 with a new library `atests/FailureModesLib.py`. It runs the nested suite `atests/_nested/failure_modes.robot`, with a test for each mode, and checks:
    - a ValueError fails with `ValueError: bad value`, and the traceback that names the library's `raise` line appears once at DEBUG;
    - `SkipExecution` skips with its message;
    - a test with `ContinuableFailure` runs its next keyword and fails with the message;
    - after `FatalError`, the next test is not run and fails as stopped by a fatal error;
    - afterwards a keyword call to the same server still returns its result.
  - **`atests/errors.robot`** expects the exact message `boom` instead of `*boom*`.

  These cover the client scenarios Remote keyword raises SkipExecution, Remote keyword raises ContinuableFailure, Remote keyword raises FatalError and Traceback of a failed remote keyword, and the server scenario Keyword call after a fatal failure.
- [ ] 4.3 Documentation (design decision 7):
  - **A new guide** `docs/src/content/docs/guides/failures.mdx`, "Failures of remote keywords", in the Guides sidebar, with the example `docs/examples/failures/`: a library that fails normally, skips, fails continuably and fails fatally, a suite with a test for each, and a `run.sh` that runs the suite twice, since the server keeps running after the fatal failure, with `--nostatusrc`, and checks the status and message of each test, the traceback and the keyword after the continuable failure with Robot's result API.
  - **The protocol page** describes `RunKeywordError` as the server fills it and the client uses it.
  - **On Status and roadmap**, the failure modes move from Planned to Available today.

  Verify with `uv run --all-packages bash docs/examples/failures/run.sh` and `npm run build` in `docs/`.

## 5. Client: log level, with its Robot test and documentation

- [ ] 5.1 The client reports `${LOG LEVEL}` in `robot/initialize` and, before a keyword call, sends `robot/set_log_level` when `${LOG LEVEL}` differs from the level it reported last in the session (design decision 4). Verify with tests in `tests/test_client_logging.py` on the fake server, which records the params of `robot/initialize` and the `robot/set_log_level` notifications (extend `tests/fake_server.py` for that). They cover:
  - the level in `robot/initialize`;
  - a notification after a change and none without one;
  - the client scenarios Log level at the start of a session and Log level changed during the run.
- [ ] 5.2 A new suite `atests/log_levels.robot` against the shared server, with a keyword in `atests/ServerProbeLib.py` that logs a TRACE, a DEBUG and an INFO message, and `LogCapture`, checks:
  - after `Set Log Level    DEBUG`, the INFO and DEBUG messages reach the log and the TRACE message does not;
  - after `Set Log Level    TRACE`, the next call also brings the TRACE message;
  - in a nested run with `--loglevel DEBUG` (`atests/_nested/log_levels.robot`), the DEBUG message arrives from the start of the session.
- [ ] 5.3 The client puts `[remote] ` in front of the DEBUG and TRACE messages from the server and of the traceback, and leaves other messages unchanged (design decision 5). Verify with `tests/test_client_logging.py` and `tests/test_client_failures.py`, and with the Robot suites of 4.2 and 5.2, which expect the mark. They cover the client scenarios Debug message from the server, Robot Framework's trace lines from both sides, Info message from the server and Traceback of a failed remote keyword is marked
- [ ] 5.4 The example server handles `robot/set_log_level`, as the protocol page says of every message of the client. Verify with `tests/test_example_server.py`, which sends the notification and expects no error for it
- [ ] 5.5 Documentation (design decision 7):
  - **The protocol page** describes `log_level` in `InitializeParams` and the notification `robot/set_log_level` in the methods table and the data structures, and `packages/protocol/README.md` lists the new method in its summary.
  - **Getting started** says that the log messages of a remote keyword follow the log level of the suite, `--loglevel` and `Set Log Level` included, and what `[remote]` means.
  - **The server reference** says that what the server logs to stderr does not depend on the log level of its clients.

  Verify with `npm run build` in `docs/` and with a check that the protocol page names every message and dataclass of `robot_jsonrpcremote_protocol`, as for `add-documentation-site`.

## 6. Integration checks

- [ ] 6.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 6.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [ ] 6.3 Run `npm ci` and `npm run build` in `docs/` and every `docs/examples/*/run.sh` with `uv run --all-packages bash`; verify all pass
- [ ] 6.4 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`):
  - **Subject:** `fix: report remote keyword failures and log levels as for local keywords`.
  - **Body:** explains the message, the failure modes and the traceback, the log level that the client reports, the mark `[remote]`, the DEBUG logging of failures on the server, and that tests matching the old message need the new one.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive` and sync its delta specs into `openspec/specs/client` and `openspec/specs/server`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-keyword-failure-reporting`.
- Set CLIENT-2 and SERVER-16 to done in `playground/anforderungen-und-ideen.md`, and note in TEST-6 that its failure-mode parts are done.
