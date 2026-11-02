# Proposal

## Why

If the TCP connection is reset while a session starts, after the client has sent its request and before the server has answered, the whole Robot Framework run ends with exit code 255 and `Unexpected error: RecursionError`. Later tests and all teardowns do not run, `output.xml` stays incomplete, `log.html` and `report.html` are not written, and servers that the suite started stay behind.

The client causes this. It cleans up the connection inside its `except` block, which links the start error and the reset to each other in a cycle of `__cause__` and `__context__`. Robot Framework follows that chain without checking for cycles.

The reset has to arrive in a short window, for example from a server that is just ending, so this is rare in normal use. A suite against a published container port, which resets connections while nothing listens behind it, did not hit it in 38 runs, because the reset came before the request was written. When it does happen, the results of the whole run are lost.

On Windows, `atests/session_start.robot` can hit it by itself. In a venv, `sys.executable` is a launcher with the real interpreter as its child, so `terminate()` and `kill()` in `atests/ServerControl.py` return while the real server still accepts connections for a moment. A connection right after the stop was accepted in 25 of 30 cases through the launcher and in 0 of 30 through the real interpreter. The test itself hit the race in 2 of about 70 runs on a Windows 11 VM, and in none of the 21 runs in CI whose logs are still available.

With the crash fixed, the same reset still makes asyncio print `Future exception was never retrieved` with a traceback (backlog item CLIENT-7), in a run that otherwise goes on normally.

Found on 2026-11-02 while testing stdio on Windows (new backlog item CLIENT-14).

## What Changes

- **Client:** a connection reset while a session starts fails only the call that started the session, like any other failed start. The run goes on, and connect retry treats it like any other failed attempt.
- **Peer:** an error that ends a peer is no longer reported as never retrieved when nobody waits for the peer's completion. A caller that waits still receives it.
- **Test helper:** the keywords of `atests/ServerControl.py` that stop the server return only when its port no longer accepts connections.
- **Tests:** unit tests for the peer, the client and the test helper, and a Robot suite with a server that resets. Its tests run in a nested Robot process, so that a regression fails a test instead of ending the outer run.
- **Docs:** no page changes. The pages do not describe this failure, and a failed start now behaves as they describe failed starts.
- **Not in this change:** the missing cycle check in Robot Framework, which can be reported there separately, and the message of the failure, which stays `JsonRpcConnectionClosedError: Connection closed before a response was received`.

Assumption recorded for review:

- CLIENT-7 is part of this change, because it is what remains of the same scenario once the crash is gone, and the fix is small.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: a new requirement that a connection reset while a session starts fails only the call that started it.
- `jsonrpc-peer`: a new requirement that an error that ends the peer is not reported as never retrieved.

## Impact

- **Client:** `_Session._run_client` in `src/JsonRpcRemote/__init__.py`.
- **Peer:** `_completion` and the done callback `_closing_done` in `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py`.
- **Tests:** `atests/ServerControl.py`, `atests/_nested/failing_import.robot` (its documentation), `tests/fake_server.py`, `tests/test_client_session.py`, `tests/test_client_connect_retry.py`, `tests/test_peer.py`; new `tests/test_server_control.py`, `atests/ResetServer.py`, `atests/connection_reset.robot` (port 8282) and `atests/_nested/reset_at_session_start.robot`.
- No change to the protocol, the public API or the dependencies. The change does not depend on the other open changes.
