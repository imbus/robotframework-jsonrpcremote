# Proposal

## Why

Libraries with the scope `GLOBAL` behave differently on the server than the client's messages and the docs suggest. Every import runs under its own token, but Robot Framework's importer caches `GLOBAL` libraries by name and arguments. All clients of a server therefore share one instance of a `GLOBAL` library, across independent test runs, and that instance survives reconnects. `SUITE` and `TEST` libraries get a new instance for every import, because the server's internal test never ends. Verified with a counter keyword in three separate sessions: `GLOBAL` returns 1, 2, 3; `SUITE` and `TEST` return 1, 1, 1.

The warning that the client logs after reconnecting therefore claims too much for a `GLOBAL` library: "the remote library was imported again, so its server-side state was reset". Its state is only reset if the server process restarted.

Found in the project review of 2026-10-27 (item SERVER-9).

## What Changes

- **Semantics:** unchanged. A `GLOBAL` library has one instance for the lifetime of the server process, shared by all clients, as Robot Framework defines `GLOBAL`.
- **Reconnect warning:** distinguishes the scopes. For a `GLOBAL` library it says that the server-side state is kept unless the server restarted.
- **Finalizing:** a client that finalizes its `GLOBAL` library does not end the shared instance. The design checks when the instance is closed, and that it is closed when the server stops.
- **Docs:** a section on the documentation site on how each library scope behaves on the server, including the sharing of `GLOBAL` libraries between clients and test runs, with a runnable example.
- **Tests:** a Robot test with a counter keyword in a `GLOBAL` library over several sessions, the part of the Robot test gaps that depends on this change; a unit test for the warning.

Assumptions recorded for review:

- `GLOBAL` libraries stay shared instead of being isolated per client. Isolating them would need a way around Robot Framework's importer cache and would change what `GLOBAL` means.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds requirements that a `GLOBAL` library is shared by all clients for the lifetime of the server, and that finalizing it for one client does not end it.
- `client`: modifies the requirement on the warning after a reconnect (from `add-client-connect-retry`) for `GLOBAL` libraries.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py` (the reconnect warning); `packages/server/src/robot_jsonrpcremote_server/_runner.py` (`_robot_finalize_library`) only if the check of the finalization finds a problem.
- **Docs:** the documentation site (library scopes and reconnects).
- **Tests:** a Robot suite with a counter library; a unit test with the fake server for the warning.
- **Order:** after `add-server-runner-tests`, `add-robot-integration-tests` and `fix-server-library-import`.
