# Proposal

## Why

An experiment during the PR #3 review (2026-10-26) sent SIGTERM to the server while a client was connected:

- **The process does not exit,** on Python 3.10 and on 3.13, although it logs "Server has stopped.".
- **On Python ≥ 3.12.1 it gets worse:** the client connection stays open, and keyword calls hang until the process is killed.

In Kubernetes, the setup from #2, a pod restart sends SIGTERM first. Keyword calls therefore hang for the termination grace period (30 seconds by default) and only then fail. The opt-in connect retry (`add-client-connect-retry`) can only take over once the connection has actually closed.

## What Changes

- **Stop sequence:** When the server is asked to stop (SIGTERM or SIGINT), it stops accepting connections and delivers the result of the keyword that is still running. Then it closes every client connection and exits with code 0, independent of the Python version.
- **Rejected requests:** Requests that need the Robot runner (importing or finalizing a library, running a keyword) and are still queued when the stop begins, or arrive afterwards, are not executed. The server answers them with the error "server is shutting down".
- **Disconnect cleanup:** Finalizing a client's libraries when it disconnects no longer waits on a stopped runner.

## Capabilities

### New Capabilities

- `server`: Behavior of the `robot-jsonrpcremote-server` runtime: hosting Robot Framework libraries for connected clients over the supported transports, and starting and stopping cleanly. This change introduces it with the requirements for stopping while clients are connected.

### Modified Capabilities

_None._

## Impact

- **Code:** in `packages/server/src/robot_jsonrpcremote_server/`
  - `__main__.py`: stop sequence, registry of active client connections;
  - `_runner.py`: reject new commands and drain queued ones once stopped;
  - `_endpoint.py`: track requests in progress.
- **API / CLI:** no new options.
- **Protocol:** unchanged.
- **Docs:** a section on stopping the server in `packages/server/README.md`.
- **Tests:**
  - unit tests for the runner's reject/drain behavior;
  - POSIX-only Robot tests: SIGTERM with a connected client, and the result of a keyword that was running at the stop;
  - a manual run of the shutdown suites with Python ≥ 3.12.1, since CI only covers 3.10 (backlog TEST-2).
