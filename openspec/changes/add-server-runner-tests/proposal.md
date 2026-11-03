# Proposal

## Why

The unit tests no longer replace Robot Framework completely. Since `fix-keyword-failure-reporting`, `tests/test_server_end_to_end.py` speaks the protocol to the real server in a process of its own, at about 0.03 s per test. With it, the unit tests run 91 % of `_runner.py` and 95 % of `_endpoint.py`, with branches counted.

A mutation test of both files on 2026-11-03 shows what can still break without a unit test noticing:

- **Finalizing a library:** that its token is gone afterwards, that the listener of a `SUITE` or `TEST` library is closed, that an unknown token is no error, and that finalizing all libraries of a connection goes on after a failure. Only one Robot test notices the listener.
- **The library definition:** the arguments of a keyword with their kinds, types and defaults, and its documentation, tags and source. The Robot suites notice only what they happen to use.
- **The default library:** an import with an empty name takes the first library of the server. This runs nowhere, in the Robot suites neither.
- **The result of `initialize`:** `support_exit` and the list of libraries.
- **A forwarded log message:** its level, its HTML flag, and that it is not meant for the console.
- **A client that is gone:** no log messages are forwarded for it, and its handshake counts as not done.
- **Paths the protocol cannot reach:** a call from the runner thread, a command without a Robot context, `wait_idle()` before the first request, a log message while no command runs, and the mapping of Robot log levels to protocol levels.

Later changes in the series rework this code (`fix-server-library-import`, `clarify-global-library-scope`) and need it guarded.

Found in the project review of 2026-10-27 (item TEST-5), and checked against the code on 2026-11-03.

## What Changes

- **Tests over the protocol:** new tests in `tests/test_server_end_to_end.py` for finalizing, the library definition, the default library, the result of `initialize` and forwarded log messages, against the real server.
- **Direct tests:** new tests in `tests/test_runner.py` and `tests/test_endpoint.py` for the paths the protocol cannot reach, without Robot Framework.
- **Bugs found:** a test that reveals a bug is marked as an expected failure that names the bug, and the bug gets a change of its own.
- No product code and no behavior change, so the change has no spec delta (`skip_specs: true`).

Assumptions recorded for review:

- No fixture runs `RobotRemoteContext.run()` in the test process, as first planned. It works, but everything above goes without it. It would be a second way to run the server, it would leave global state of Robot Framework changed in the test process, such as `text.MAX_ERROR_LINES` and the console logger, and it would skip the protocol.
- The branches `if lib is None` in `_robot_import_library` and `_robot_run_keyword` stay untested: Robot's `get_library` raises instead of returning `None`, so they cannot run. `fix-server-library-import` rewrites that path and can remove them.
- `__main__.py` and `_signals.py` stay out of this change, which is about the runner and the endpoint.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **Tests:** new tests in `tests/test_server_end_to_end.py`, `tests/test_runner.py` and `tests/test_endpoint.py`.
- **Code:** none.
- **Order:** before `fix-server-library-import` and `clarify-global-library-scope`, whose code these tests guard.
