# Proposal

## Why

Connect retry repeats every failure of a session start, not only a failed connection. When a server is reachable but rejects the library import, the client still waits for the whole `rpc_connect_retry_timeout`. Two examples are a library that the server does not serve and a library that fails to import on the server. The error then reads `Could not connect to … within 10 seconds (11 attempts): … Library 'MyLibary' is not available.`, although the connection worked at the first attempt. Each attempt runs the import again in the server's runner, and all other clients of the server wait for it. A URI that the client cannot use, such as `htp://…`, waits for the whole window as well. Without connect retry, all of these fail at once with their own message.

Found in the review of `add-documentation-site` (item CLIENT-11).

## What Changes

- **Client:** connect retry repeats only connection failures. These are the `OSError`s, such as a refused or reset connection, a closed connection, a pipe that does not exist and the timeout of an attempt, and the new error response `SHUTTING_DOWN`. Any other failure fails the call at once, with the same error as without connect retry. Examples are an error response of the server, such as `Library 'MyLibary' is not available.` or the error of a library that fails to import, and an invalid URI. Such a failure does not begin an outage and does not count as a failed attempt.
- **Protocol:** `RobotJsonRpcErrorCode` gets `SHUTTING_DOWN = -32002`.
- **Server:** it answers a request that it no longer runs because it is stopping with the code `SHUTTING_DOWN` instead of `-32603`. The message `server is shutting down` stays. During a restart, a client can still reach the stopping server and get this answer to its import; with the new code, connect retry tries again instead of failing.
- **Docs:** the guide Lost connections and connect retry says which failures are repeated. The protocol reference lists the new code. The server reference names the code of `server is shutting down`.
- **Tests:** unit tests of the client against the fake server, for a refused import, an import that fails on the server, a stopping server and an invalid URI. Unit tests of the server for the new code. Robot tests of a refused import and of a library that fails to import, both with connect retry.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: the requirement that connect retry repeats every connection attempt now names the failures that it repeats, and that every other failure fails at once.
- `server`: the requirement that requests that can no longer run are rejected now names the code `SHUTTING_DOWN` (`-32002`).

## Impact

- **Code:**
  - `src/JsonRpcRemote/__init__.py` (`_connect_with_retry`).
  - `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py` (`RobotJsonRpcErrorCode`).
  - `packages/server/src/robot_jsonrpcremote_server/_runner.py` (`_shutting_down`).
- **Protocol:** a new error code. Client and server change together; there is no compatibility with older versions in pre-alpha.
- **Docs:**
  - `docs/src/content/docs/guides/lost-connections.mdx`.
  - `docs/src/content/docs/reference/protocol.mdx`.
  - `docs/src/content/docs/reference/server.mdx`.
- **Tests:**
  - `tests/client/test_client_connect_retry.py`.
  - `tests/server/test_runner.py` and `tests/server/test_endpoint.py`.
  - `atests/connection/connect_retry.robot`.
