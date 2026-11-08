# Proposal

## Why

The warning that the client logs after a reconnect claims too much for a library with the scope `GLOBAL`: "the remote library was imported again, so its server-side state was reset". Robot Framework's importer caches a `GLOBAL` library by its name and import arguments, so all clients of a TCP server share one instance of it, across sessions and test runs, and the instance survives a reconnect. Its state is only reset if the server process restarted. Over stdio, every session has a server process of its own, so there the warning is right for every scope. The pages Sessions and rpc_scope and Lost connections already describe this sharing; only the warning, and the copy of it on the second page, say otherwise.

Found in the project review of 2026-10-27 (item SERVER-9).

## What Changes

- **Semantics:** unchanged. A `GLOBAL` library has one instance per set of import arguments for the lifetime of the server process, shared by all clients, as Robot Framework defines `GLOBAL`.
- **Reconnect warning:** for a `GLOBAL` library over a `tcp://` URI, it says that the server-side state is kept unless the server restarted. For the other scopes, and over stdio, where the client starts a new server process, it keeps saying that the state was reset.
- **Finalizing:** unchanged. A client that finalizes its `GLOBAL` library leaves the shared instance and the library's listeners to the other clients, and the listeners are closed when the server stops. Tests pin this.
- **Docs:** the page Lost connections gives the end of the warning for a `GLOBAL` library over TCP, next to the quoted one, and says what a reconnect over stdio leaves.
- **Tests:** a Robot suite with counter libraries of the three scopes, the `GLOBAL` one with a listener of its own, over several sessions and clients, a finalize, a stop of the server and a reconnect; a Robot test of a reconnect over stdio; a unit test of the warning.

Assumptions recorded for review:

- `GLOBAL` libraries stay shared instead of being isolated per client. Isolating them would need a way around Robot Framework's importer cache and would change what `GLOBAL` means.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds requirements that a `GLOBAL` library is shared by all clients for the lifetime of the server, and that finalizing it for one client leaves it and its listeners to the others until the server stops.
- `client`: modifies the requirement on the warning after a reconnect, for `GLOBAL` libraries over TCP.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py` (the reconnect warning).
- **Docs:** `docs/src/content/docs/guides/lost-connections.mdx`.
- **Tests:** `tests/test_client_connect_retry.py` with `tests/fake_server.py`; new test libraries and the suite `atests/global_library.robot`; `atests/stdio_connect_retry.robot` with `atests/stdio_vars.py`.
- **Order:** independent of the other changes.
