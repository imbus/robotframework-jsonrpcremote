# Proposal

## Why

Issue #2 (Fabian Tsirogiannis) describes Robot Framework tests against a GUI application in Kubernetes. The JSON-RPC server runs as a sidecar in the application pod. Some tests patch the Deployment, which restarts the pod and with it the server. A few seconds later the server is reachable at the same address again, but the client cannot recover. The current workaround calls private methods of `JsonRpcRemote` in a retry loop.

After the earlier changes, the client detects and reports a lost connection clearly (`fix-client-lost-connection`), and the server closes connections when it stops (`fix-server-shutdown-with-clients`). What is still missing is the opt-in to wait for the server and reconnect.

## What Changes

- **New options:**
  - `rpc_connect_retry_timeout`, default `0`, retry disabled;
  - `rpc_connect_retry_interval`, default `1s`.

  Both accept seconds or Robot Framework time strings, also as plain strings from Python, and so does `rpc_timeout` now. Invalid values fail the import. The options are not forwarded to the remote library.
- **Retry window:** With retry enabled, every connection attempt is repeated every interval until it succeeds or the window has passed. That covers the library import, a new session at a scope boundary, and replacing a lost session. Each attempt stays limited by `rpc_timeout`.
- **Giving up:** at most once per outage. After the window has passed, every further call makes exactly one attempt without waiting, until a connection succeeds; the next outage gets the full window again.
- **Lost session:** After a lost connection, the next call replaces the session; this re-imports the remote library. The client logs a warning with the cause of the loss, the time until it reconnected, the number of attempts and the reset of the server-side state; for `stdio:` this includes the exit code. A keyword that was running at the moment of the loss is still never sent again.
- **Definition check:** After such a reconnect, the client compares the full library definition with the one registered at import. If it changed, the library cannot be used until the session ends according to `rpc_scope`.
- **Docs:** The README documents the options and extends the section "Lost connections".

Closes #2.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`:
  - **Modified:** the requirement "A lost connection fails every later call until the session ends" now applies only without connect retry.
  - **Added:** requirements for the options, the retry window, giving up once per outage, the reconnect warning and the definition check.

## Impact

- **Code:** `src/JsonRpcRemote/__init__.py`, namely the options and their parsing in `JsonRpcRemote.__init__`, the retry loop around `_connect()`, the outage and lost-session state in `_start_session()`, and the definition check.
- **API:**
  - two new library options;
  - `rpc_timeout` now also accepts time strings; numbers keep working, and only its type hint changes to `float | str`.
- **Behavior:** unchanged without the opt-in, except that `rpc_timeout` accepts time strings.
- **Docs:** `README.md` (argument list, client options that are not forwarded, section "Lost connections").
- **Tests:**
  - unit tests with the fake server: options, retry window, giving up, warning, definition check;
  - Robot suites for TCP and `stdio` with self-written helpers, for example starting the isolated server without waiting for its port.
- **Order:** `fix-client-lost-connection` must be archived before this change, because this delta modifies one of its requirements.
