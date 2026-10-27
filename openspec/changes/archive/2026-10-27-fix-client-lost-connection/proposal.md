# Proposal

## Why

When the connection of an established session is lost (server crash, container restart, server stopped), the client does not recognize it as a loss. Every later call fails with `RuntimeError: Event loop is not initialized yet`, or since `fix-client-stranded-calls` with a generic `ConnectionError: Connection to '<uri>' is closed`. Neither names a cause. Fabian Tsirogiannis reported this in #2; in his case, a Kubernetes pod with the server restarted during a suite.

A clear, consistent error with its cause is what users need to understand a failed test. It is also the base for the opt-in connect retry (`add-client-connect-retry`).

## What Changes

- **Detection:** The client detects that the connection of an established session ended without the client closing it.
- **Later calls:** Every following call in that session fails with `ConnectionError: Connection to '<uri>' was lost: <cause>`. That lasts until the session ends according to `rpc_scope`; the next call after that starts a new session as usual. Without opt-in, the client does not reconnect on its own.
- **Running keyword:** A keyword that is running when the connection is lost fails with `ConnectionError: Connection to '<uri>' was lost while running keyword '<name>': <cause>`. It is never sent again.
- **Cause:** either "the connection was closed by the server" or the type and message of the error that ended the connection. For `stdio:` the exit code of the server process is added.
- **No false alarm:** When the client ends a session itself (`rpc_scope`, library teardown), that is never reported as a loss.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client` (introduced by `fix-client-session-error-state`): adds the requirements for detecting and reporting a lost connection.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py`, namely `_Session` (closed-by-client flag, loss state, recorded cause), `JsonRpcRemote._start_session` and `JsonRpcRemote.run_keyword`.
- **API:** no new options. Only the error messages for these situations change.
- **Docs:** a new README section on what happens when the connection is lost. `add-client-connect-retry` extends it later.
- **Tests:**
  - unit tests against the fake server from `fix-client-session-error-state`;
  - new, self-written Robot helpers: a keyword that kills the isolated server, and a probe library whose keyword ends the server process during the call;
  - a TCP suite and a POSIX-only `stdio` suite.
