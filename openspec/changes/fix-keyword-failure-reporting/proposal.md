# Proposal

## Why

When a remote keyword fails, Robot Framework shows a message that is hard to read, and how the keyword failed gets lost. A keyword that raises `ValueError("bad value")` appears as:

`Error executing keyword 'Fail Typed': RunKeywordError(message='ValueError: bad value', type=None, traceback=None, mode=None)`

- The client builds the message from the `repr` of the protocol's error object.
- The server only fills `message`. `type`, `traceback` and `mode` stay empty, although the protocol defines them.
- A keyword that skips the test (`SkipExecution`), fails continuably (`ContinuableFailure`) or stops the whole run (`FatalError`) arrives as a normal failure. Robot then fails the test instead of skipping it, continuing it or stopping the run.
- The server runs Robot Framework at log level INFO, so the DEBUG and TRACE messages of a remote library, and the traceback that Robot logs at DEBUG, never reach the client, whatever log level the suite uses.

The Robot suite `errors.robot` only checks that the message contains `boom`, so it did not notice.

Found in the project review of 2026-10-27 (item CLIENT-2); the log levels were found while designing this change (item SERVER-16).

## What Changes

- **Server:** fills the error of a failed keyword completely: the message as Robot Framework formats it for a local keyword, the exception type, the traceback, and the failure mode (skip, continuable, fatal) taken from the exception. A fatal failure ends only that keyword call; the server keeps running, as it does today.
- **Log levels:** the client tells the server its log level when a session starts and again when it changes, for example with `Set Log Level`. The server forwards the log messages of its libraries from that level on, DEBUG and TRACE included, and none below it. The client marks DEBUG and TRACE messages from the server with `[remote] `, because at these levels they stand beside its own.
- **Client:** reports the failure the way Robot reports a failing local keyword. The message is the remote message without a prefix or a `repr`. A skip skips the test, a continuable failure lets the test continue, and a fatal error stops the run. The remote traceback goes to the log at DEBUG level, like the traceback of a local keyword.
- **Compatibility:** tests that match the old message format, for example with `Run Keyword And Expect Error`, need the new message. Before 1.0, this is not a breaking change.
- **Tests:** unit tests on both sides; Robot tests for the exact message and for skip, continuable and fatal failures, the parts of the Robot test gaps that depend on this change.
- **Docs:** a new guide on the documentation site on how failures of remote keywords appear in Robot Framework, with runnable examples for a normal, a skipped, a continuable and a fatal failure. The protocol page describes the fields of `RunKeywordError` as the server fills them and the client uses them, and the client's log level in `robot/initialize` and `robot/set_log_level`; Getting started says that log messages of remote keywords follow the log level of the suite. On Status and roadmap, the failure modes move from Planned to Available today.

Decisions confirmed on 2026-10-31:

- The message is exactly the remote message, as Robot Framework shows it for a local keyword; Robot already shows which keyword failed, so the client does not repeat the keyword name.
- The traceback of a failed keyword is always sent and logged at DEBUG level, because it shows the hosted library's code, which the test author needs. `fix-rpc-error-responses` limits tracebacks only for protocol-level errors.

Decision confirmed on 2026-11-01:

- DEBUG and TRACE messages from the server, the traceback included, are marked with `[remote] `, so that they can be told from the client's own. Messages at other levels stay unchanged.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: adds requirements for the message of a failed remote keyword, for skip, continuable and fatal failures, for the remote traceback in the log, for reporting its log level, and for marking DEBUG and TRACE messages from the server.
- `server`: adds requirements that the error of a failed keyword carries its message, type, traceback and failure mode, that a fatal failure does not stop the server, and that log messages are forwarded from the client's log level on.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/_endpoint.py` (`initialize`, `run_keyword`, the log forwarding), `_runner.py` (`_robot_run_keyword`, the log level per command), `src/JsonRpcRemote/__init__.py` (`JsonRpcRemote.run_keyword`, the session start).
- **Protocol:** the existing fields `type`, `traceback` and `mode` of `RunKeywordError` are now filled. `InitializeParams` gets the optional field `log_level`, and the client gets the notification `robot/set_log_level` with `SetLogLevelParams`.
- **Tests:** unit tests for the server's error and for the client's mapping; `atests/errors.robot` and a library that skips, fails continuably and fails fatally.
- **Docs:** a new guide under `docs/src/content/docs/guides/` with its examples in `docs/examples/`, `docs/src/content/docs/reference/protocol.mdx` and `docs/src/content/docs/roadmap.mdx`.
- **Order:** after `add-documentation-site`, so the new messages are documented on the site; before `fix-rpc-error-responses`, which changes how the client reports protocol-level errors in the same code path.
