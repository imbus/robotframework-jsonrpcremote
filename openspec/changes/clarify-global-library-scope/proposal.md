# Proposal

## Why

The warning that the client logs after a reconnect claims too much for a library with the scope `GLOBAL`: "the remote library was imported again, so its server-side state was reset". Robot Framework's importer caches a `GLOBAL` library by its name and import arguments, so all clients of a server that they connect to over `tcp://` or `pipe://<name>` share one instance of it, across sessions and test runs, and the instance survives a reconnect. Its state is only reset if the server process restarted. With a `stdio:` or `pipe:<command>` URI, the client starts a server process of its own for every session, so there the warning is right for every scope. The pages Sessions and rpc_scope and Lost connections already describe this sharing; only the warning, and the copy of it on the second page, say otherwise.

Found in the project review of 2026-10-27 (item SERVER-9).

## What Changes

- **Semantics:** unchanged. A `GLOBAL` library has one instance per set of import arguments for the lifetime of the server process, shared by all clients, as Robot Framework defines `GLOBAL`.
- **Reconnect warning:** for a `GLOBAL` library on a server that the client did not start, over `tcp://` or `pipe://<name>`, it says that the server-side state is kept unless the server restarted. For the other scopes, and over `stdio:` and `pipe:<command>`, where the client starts a new server process, it keeps saying that the state was reset.
- **Finalizing:** unchanged. A client that finalizes its `GLOBAL` library leaves the shared instance and the library's listeners to the other clients, and the listeners are closed when the server stops. Tests pin this.
- **Docs:** the page Lost connections gives the end of the warning for a `GLOBAL` library over `tcp://` and `pipe://`, next to the quoted one, and says what a reconnect leaves with a `pipe:` or `stdio:` URI with a command.
- **Tests:** a Robot suite whose tests each start a server of their own, with counter libraries of the three scopes, the `GLOBAL` one with a listener of its own, over several sessions and clients, a finalize, a stop of the server and a reconnect over TCP; Robot tests of a reconnect over `stdio:` and `pipe:<command>`; a unit test of the warning over `tcp://` and `pipe://<name>`.

Assumptions recorded for review:

- `GLOBAL` libraries stay shared instead of being isolated per client. Isolating them would need a way around Robot Framework's importer cache and would change what `GLOBAL` means.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds requirements that a `GLOBAL` library is shared by all clients for the lifetime of the server, and that finalizing it for one client leaves it and its listeners to the others until the server stops.
- `client`: modifies the requirement on the warning after a reconnect, for `GLOBAL` libraries on a server that the client did not start.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py` (the reconnect warning).
- **Docs:** `docs/src/content/docs/guides/lost-connections.mdx`.
- **Tests:** `tests/test_client_connect_retry.py` with `tests/fake_server.py`; new test libraries, the suite `atests/global_library.robot` and the nested suite `atests/_nested/counters.robot`; `atests/stdio_connect_retry.robot` with `atests/stdio_vars.py`; `atests/pipe_connect_retry.robot` with `atests/pipe_vars.py`.
- **Order:** after `add-pipe-transport`, whose pipe URIs the warning covers.
