# Proposal

## Why

A server that cannot start reports it as a success, and a stdio server whose stdin it cannot read waits forever. Both came up on 2026-10-27 while verifying `fix-server-shutdown-with-clients`:

- **A failed start exits with code 0.** If the TCP port is in use, or stdio mode cannot use stdin or stdout (a regular file, a closed stdin), the server thread dies. The main thread still logs "Server is up and running", waits 5 seconds, logs "Server failed to start." and exits with code 0. A supervisor such as Kubernetes or systemd sees a clean exit, and the log first claims the opposite of what happened.
- **stdin `/dev/null` hangs the stdio server.** The event loop cannot watch `/dev/null` (epoll rejects it). The failure surfaces only as a logged callback error, so the server neither receives data nor sees EOF and waits until it is killed. Docker gives a container started without `-i` exactly this stdin, so a misconfigured stdio container hangs instead of failing.

## What Changes

- **Start failures:** When the server cannot start, it logs the reason as an error and exits with a non-zero exit code as soon as the start has failed. It no longer reports that it is up and running first, and it no longer waits for a start timeout.
- **stdin in stdio mode:** In stdio mode, the server checks at start that its stdin is open and that the event loop can watch it, as it can a pipe, a socket or a terminal. Otherwise, for example for `/dev/null` or a regular file, the start fails with an error that says so.
- **Docs:** the server README states that a failed start exits with a non-zero exit code, and its stdio notes say which stdin stdio mode needs.

Assumptions recorded for review:

- The exit code for a failed start is 1.
- The fix is not part of the PR #3 findings: its commits carry neither `Refs #2` nor a co-author.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server` (introduced by `fix-server-shutdown-with-clients`): adds the requirements for a failed start and for the stdin that stdio mode accepts.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/__main__.py`, namely `run()`, `run_server()` and `_stdio_streams()`.
- **CLI:** no new options. A failed start now exits with code 1 instead of 0, and does so at once instead of after 5 seconds.
- **Protocol / client:** unchanged.
- **Docs:** `packages/server/README.md`.
- **Tests:** unit tests for the stdin check, and tests that start the real server as a subprocess with a port in use and, on POSIX, with stdin `/dev/null`.
