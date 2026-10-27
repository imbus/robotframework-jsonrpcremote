# Proposal

## Why

When a session fails to start (connecting or the handshake fails), the client does not clean up what it opened. A TCP connection is only closed implicitly, when the worker's event loop is torn down. For a `stdio:` URI, nothing waits for the spawned server process: it is not reaped and its exit code is lost. Fabian Tsirogiannis found this in #2 and PR #3. With connect retries (`add-client-connect-retry`), every failed attempt could otherwise leave a server process behind.

## What Changes

- When connecting or the handshake fails, the client closes the connection and, for `stdio:`, waits for the spawned server process to exit **before** it reports the failure. Escalation to terminate/kill after `rpc_timeout` works the same way as at normal teardown.
- The client records the exit code of a spawned server once it has been reaped. Later changes use it in their messages.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client` (introduced by `fix-client-session-error-state`, which is archived first): adds the requirement that a failed session start releases its resources.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py`, namely the start-failure path of `_Session._run_client` and the recording of the exit code in `_Session.close_connection`.
- **API:** no change.
- **Behavior:** reporting a failed start waits for the cleanup. Normally that takes milliseconds; with a `stdio:` server that ignores EOF, it can take up to the terminate/kill escalation.
- **Tests:** unit tests against the fake server from `fix-client-session-error-state`, plus a POSIX-only `stdio:` test against the real server.
