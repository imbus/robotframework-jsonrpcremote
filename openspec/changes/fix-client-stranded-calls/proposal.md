# Proposal

## Why

The end of a session has three robustness gaps. The first was found by Fabian Tsirogiannis in PR #3; the second showed up in the SIGTERM experiment of the PR review:

- **Stranded calls hang forever.** A keyword call is handed to the session's worker thread just as its event loop shuts down. The call is never run and its result never resolved, so the Robot Framework thread waits forever.
- **Ending a session can raise.** `_finalize_session` lets errors from stopping the peer escape, for example a `TimeoutError` or `RuntimeError: Event loop is closed`. They surface as listener errors at the end of a test or suite, as `__del__` noise, or as a traceback on stderr at interpreter exit.
- **A failed start prints a traceback.** The worker thread dies with the exception, and Python prints "Exception in thread …" to stderr, although the error is already reported to the caller. With connect retries (`add-client-connect-retry`), that would be one traceback per attempt.

## What Changes

- Keyword calls go through a single submission point that knows whether the session's worker is still running:
  - A call on a session that has ended fails at once with a `ConnectionError`.
  - A call stranded by the shutdown fails with a `ConnectionError` when the worker ends.
- Ending a session never raises:
  - Each teardown step is bounded by `rpc_timeout`, and its errors are suppressed.
  - The `stdio` process backstop and the release of the session's resources always run.
- The worker thread no longer lets exceptions escape. The errors are reported where they belong (start error, failed call) and logged at debug level.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client` (introduced by `fix-client-session-error-state`): adds three requirements:
  - calls never hang on an ended session;
  - ending a session never raises;
  - session errors are not printed by the worker thread.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py`, namely `_Session` (submission point, worker thread body), `_finalize_session` and `JsonRpcRemote.run_keyword`. A module logger is added for the debug output.
- **API:** no change.
- **Behavior:** for a keyword call on an ended session, the interim `RuntimeError: Event loop is not initialized yet` becomes `ConnectionError: Connection to '<uri>' is closed`. `fix-client-lost-connection` refines this message with the cause.
- **Tests:** unit tests using the fake server from `fix-client-session-error-state` and fakes for the session's event loop.
