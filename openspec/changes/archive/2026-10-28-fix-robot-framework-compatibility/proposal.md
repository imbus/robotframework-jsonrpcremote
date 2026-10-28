# Proposal

## Why

The client and the server declare `robotframework>=7.0`, and both READMEs say the same, but only Robot Framework 7.4 and later work:

- **Robot Framework 7.0:** the server does not start. It imports `NotSet` from `robot.utils`, which only exists since 7.1.
- **Robot Framework 7.1 to 7.3:** forwarding server log messages fails. The client passes `console` to `logger.write()`, a parameter added in 7.4. The `TypeError` in the notification handler drops the message, and the client's peer answers the notification with an error response to the server.

The Robot suites confirm it: on 7.0 every suite fails because the server exits with code 1, on 7.1.1, 7.2.2 and 7.3.2 the test `Server Log Is Forwarded To The Client` fails, and 7.4.2 passes. CI only tests the version locked in `uv.lock` (7.5), so the declared minimum drifted unnoticed.

The same notification handler loses messages in a second case. While no keyword call is running, for example while the server finalizes the library at the end of a session, it writes the message from the session's worker thread. Robot Framework ignores log messages from threads other than the ones it runs tests in, so the message disappears. The code carries a TODO for this case.

Found in the project review of 2026-10-27 (items BUILD-1 and CLIENT-4).

## What Changes

- **Server:** recognizes an argument without a default by `robot.utils.NOT_SET`, which every Robot Framework 7 release has and uses as that marker, instead of by the class `NotSet`.
- **Client:** passes `console` to `logger.write()` only on Robot Framework versions that support it, and writes a console message separately on older versions. The server of this project never sets `console`; the separate path is for other server implementations.
- **Log messages outside a keyword call** are no longer dropped. The client hands them to Robot Framework from the thread that runs the tests, so they are treated like messages that a local library logs at the same moment: while the library is imported, Robot Framework writes info messages only to its syslog and shows warnings and errors; when a keyword call starts a new session, they appear in that keyword's log. This project's server sends such messages when it finalizes a library; it does not forward the messages a library logs while it is imported, which is left to a separate change.
- **Minimum version:** Robot Framework 7.2 instead of 7.0, because 7.0 and 7.1 fail for further reasons (see the result of the first assumption).
- **Verification:** the unit tests and Robot suites run locally against Robot Framework 7.0, 7.1, 7.2, 7.3, 7.4 and 7.5. The CI job that keeps the minimum version tested follows in `add-ci-version-matrix`.

Assumptions recorded for review:

- Robot Framework 7.0 stays the minimum. Every other Robot Framework API that the client and the server use already exists in 7.0, including support for asynchronous keywords (checked on 2026-10-28). If 7.0 still shows incompatibilities that are not as cheap to fix, the minimum is raised to the oldest version that passes, in the `pyproject.toml` files and both READMEs.
  **Result (2026-10-28):** 7.0 and 7.1 fail for further reasons. On 7.0 the server passes `named_args` to `running.Keyword`, which exists only since 7.1, so every keyword call fails; on 7.1 the server forwards no log messages at all. 7.2 to 7.5 pass, so the minimum is raised to 7.2.
- A log message that arrives outside a keyword call is handed to Robot Framework from its main thread at the next opportunity, for example when the import of the library returns, and messages keep the order in which they arrived.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: adds requirements that server log messages are forwarded on every supported Robot Framework version, also when they arrive outside a keyword call.
- `server`: adds the requirement that the server works with every supported Robot Framework version.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/_runner.py` (`_robot_import_library`), `src/JsonRpcRemote/__init__.py` (`_ClientEndpoint._log_notification` and the handling of `callback_loop`).
- **Dependencies:** `robotframework>=7.2` instead of `>=7.0`, in both `pyproject.toml` files, both READMEs and `uv.lock`.
- **Behavior:** unchanged on Robot Framework 7.4 and later, except that log messages outside a keyword call now reach Robot Framework like those of a local library.
- **Tests:** unit tests for both paths of the log handler; the local runs against the versions above, each in its own environment.
- **Order:** first change of the series from the review; `add-ci-version-matrix` builds on it.
