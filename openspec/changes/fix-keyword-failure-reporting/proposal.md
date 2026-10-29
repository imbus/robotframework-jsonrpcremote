# Proposal

## Why

When a remote keyword fails, Robot Framework shows a message that is hard to read, and how the keyword failed gets lost. A keyword that raises `ValueError("bad value")` appears as:

`Error executing keyword 'Fail Typed': RunKeywordError(message='ValueError: bad value', type=None, traceback=None, mode=None)`

- The client builds the message from the `repr` of the protocol's error object.
- The server only fills `message`. `type`, `traceback` and `mode` stay empty, although the protocol defines them.
- A keyword that skips the test (`SkipExecution`), fails continuably (`ContinuableFailure`) or stops the whole run (`FatalError`) arrives as a normal failure. Robot then fails the test instead of skipping it, continuing it or stopping the run.

The Robot suite `errors.robot` only checks that the message contains `boom`, so it did not notice.

Found in the project review of 2026-10-27 (item CLIENT-2).

## What Changes

- **Server:** fills the error of a failed keyword completely: the message as Robot Framework formats it for a local keyword, the exception type, the traceback, and the failure mode (skip, continuable, fatal) taken from the exception.
- **Client:** reports the failure the way Robot reports a failing local keyword. The message is the remote message without a prefix or a `repr`. A skip skips the test, a continuable failure lets the test continue, and a fatal error stops the run. The remote traceback goes to the log at DEBUG level, like the traceback of a local keyword.
- **BREAKING** for tests that match the old message format, for example with `Run Keyword And Expect Error`.
- **Tests:** unit tests on both sides; Robot tests for the exact message and for skip, continuable and fatal failures, the parts of the Robot test gaps that depend on this change.
- **Docs:** a page on the documentation site on how failures of remote keywords appear in Robot Framework, with runnable examples for skip, continuable and fatal failures.

Assumptions recorded for review:

- The message is exactly the remote message; Robot already shows which keyword failed, so the client does not repeat the keyword name.
- The traceback of a failed keyword is always sent, because it shows the hosted library's code, which the test author needs. `fix-rpc-error-responses` limits tracebacks only for protocol-level errors.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: adds requirements for the message of a failed remote keyword, for skip, continuable and fatal failures, and for the remote traceback in the log.
- `server`: adds the requirement that the error of a failed keyword carries its message, type, traceback and failure mode.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/_endpoint.py` (`run_keyword`), `_runner.py` (`_robot_run_keyword`), `src/JsonRpcRemote/__init__.py` (`JsonRpcRemote.run_keyword`).
- **Protocol:** unchanged; the existing fields `type`, `traceback` and `mode` of `RunKeywordError` are now filled.
- **Compatibility:** an older server leaves the new fields empty; the client then reports a normal failure with the message alone.
- **Tests:** unit tests for the server's error and for the client's mapping; `atests/errors.robot` and a library that skips, fails continuably and fails fatally.
- **Order:** after `add-documentation-site`, so the new messages are documented on the site; before `fix-rpc-error-responses`, which changes how the client reports protocol-level errors in the same code path.
