# Proposal

## Why

The client keeps a single error per session (`last_error`) and re-raises it on every later call. Fabian Tsirogiannis found the two problems this causes in #2 and PR #3:

- **A failed keyword call poisons the session.** If a call fails at the RPC level, every later call in the session re-raises that error, even calls that would succeed. That happens when the request cannot complete (since `fix-peer-pending-requests` this is a `JsonRpcConnectionClosedError`) or when the server answers with a JSON-RPC error.
- **A failed session start sticks.** If a session fails to start (connection refused, handshake error, timeout), it is kept anyway. Every later call re-raises the same error without trying to connect again, until the test or suite ends.

## What Changes

- The session's error state describes only why the session failed to start. Keyword failures and the end of a connection no longer change it.
- A keyword call that fails affects only that call.
- `JsonRpcRemote` keeps a session only after it started successfully. A failed start raises for the call that triggered it and leaves no session behind, so the next call makes a fresh connection attempt.
- A session that does not finish starting within `rpc_timeout` is stopped before the `TimeoutError` is raised, so no worker thread or half-open connection is left behind.
- Interim behavior: after a lost connection, later calls fail again with `RuntimeError: Event loop is not initialized yet`, instead of re-raising a stored connection error. `fix-client-lost-connection` replaces this with a clear `ConnectionError`.

## Capabilities

### New Capabilities

- `client`: Behavior of the `JsonRpcRemote` Robot Framework library: starting, using and ending sessions with a remote server, and how failures are reported. This change introduces it with the requirements for failed keyword calls and failed session starts.

### Modified Capabilities

_None._

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py`: the error state of `_Session`, `_Session.run_keyword`, `_Session._run_client`, `JsonRpcRemote._start_session`.
- **API:** no change to library arguments, keywords or the protocol.
- **Behavior:** after a failed start, every call makes its own connection attempt. With an unreachable host, each call can take up to `rpc_timeout` instead of failing at once.
- **Tests:** a new in-process fake JSON-RPC server for client unit tests (reused by the following client changes), new unit tests, and a Robot suite that restarts an isolated server between tests.
- **Docs:** none. The README does not describe the old behavior.
