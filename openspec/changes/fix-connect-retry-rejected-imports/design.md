# Design

## Context

See proposal.md for the motivation. The current setup:

- `_connect_with_retry` in `src/JsonRpcRemote/__init__.py` wraps `_connect()` in `except Exception`. `_connect()` starts a session, which connects, runs the handshake and imports the library. It raises the start error of the session or a `TimeoutError` if the session did not start within `rpc_timeout`. Every failed attempt begins an outage or counts in it. With retry, the attempt is repeated until the window has passed. Then the call fails with `ConnectionError: Could not connect to … within … (n attempts): <last error>`.
- An error response reaches `_connect_with_retry` as a `JsonRpcResponseError` with `code` and `message`. Without retry, `_start_session` turns it into a `RemoteError` with the server's message. With retry, it is wrapped in the `ConnectionError` after the window.
- `JsonRpcConnectionClosedError` is a `ConnectionError`. The timeout of an attempt is a `TimeoutError`. A refused or reset connection and a pipe or command that does not exist are `OSError`s as well. An invalid URI is a `ValueError`. A response that the client cannot read is a `JsonRpcResponseError` too.
- The server's runner answers requests that it no longer runs because it is stopping with `_shutting_down()`, that is `-32603` (`INTERNAL_ERROR`) with the message `server is shutting down`. A library that fails to import is also answered with `-32603`, by the peer, with the message of the exception. A library that the server does not serve gets `-32602`.
- `RobotJsonRpcErrorCode` in the protocol package has `NOT_INITIALIZED = -32000` and `KEYWORD_NOT_FOUND = -32001`. JSON-RPC 2.0 leaves -32000 to -32099 to the server's own errors.
- The server keeps accepting connections for a moment after a stop began (SERVER-15). During a restart, a client can therefore connect to the stopping server and get `server is shutting down` as the answer to its import.

A probe on the current code with the fake server: a refused import with a window of 2 seconds took 2.0 seconds and 11 imports and ended with `ConnectionError: Could not connect to … within 2 seconds (11 attempts): JsonRpcResponseError: RPC Error -32602: Library 'FakeLib' is not available.`. Without retry it ended at once with `RemoteError: Library 'FakeLib' is not available.`. A URI `htp://…` took 2.0 seconds as well.

## Goals / Non-Goals

**Goals:**

- With connect retry, a failure that another attempt cannot fix fails the call just as without connect retry, with the same error and after a single attempt.
- A restart in which the client still reaches the stopping server stays a case for connect retry.

**Non-Goals:**

- Telling a server process that cannot start from one that starts slowly. A `stdio:` or `pipe:<command>` server that exits before the handshake closes the connection. That is a connection failure and stays one; a wrapper script may wait for something before it starts the server.
- The failures of keyword calls. They are never repeated; nothing changes there.
- SERVER-15, the server that accepts connections while it stops.

## Decisions

### Repeat `OSError` and `SHUTTING_DOWN`, fail at once on everything else

`_connect_with_retry` asks one question about each failure: could another attempt succeed? Two kinds of failure qualify:

- An `OSError`. This covers refused, reset and closed connections (`JsonRpcConnectionClosedError` included), the timeout of an attempt, and a pipe, socket or command that does not exist.
- A `JsonRpcResponseError` with the code `SHUTTING_DOWN`.

Every other failure is raised as it is, before it touches the outage. Without retry, the call already fails that way, so `_start_session` turns an error response into the `RemoteError` with the server's message for both paths. The check sits in front of the existing bookkeeping. It holds with and without retry, so a failure that is no connection failure never begins an outage and never counts as an attempt. The INFO message `Connected to … after … (n attempts)` and the reconnect warning count only real connection attempts.

Daniel chose this rule over the narrower one, which would let only error responses fail at once and keep repeating everything else, such as an invalid URI. The rule matches the sketch in the backlog: repeat only connection failures.

Alternative considered: a list of the error responses that fail at once, such as `-32602`. Any code that a future server sends would then be repeated by default, and a library that fails to import has the same code as a stopping server.

### A code of its own for a stopping server

`RobotJsonRpcErrorCode` gets `SHUTTING_DOWN = -32002`, and `_shutting_down()` in the runner uses it. The message stays `server is shutting down`, and the client shows only the message, so Robot Framework shows the same text as before. The protocol reference lists the code.

Alternatives considered:

- Comparing the message with `server is shutting down`. That would tie the client to the wording of one server; another server written against the protocol could not take part. Daniel chose the code.
- Not repeating a stopping server either. An import during a restart would then fail, although the new server is ready seconds later.

The code applies to every request that the runner no longer runs: imports, keyword calls and finalizing. Only the import matters for connect retry. For keyword calls, the message stays the same and the call fails as before.

### Tests

- **Client unit tests** in `tests/client/test_client_connect_retry.py`, with the fake server, which can answer a request with a scripted `JsonRpcResponseError`:
  - `-32602` and `-32603` on the import fail at once with the `RemoteError` of the message and a single import.
  - `-32002` on the first import is followed by a second attempt that succeeds.
  - `-32002` without retry fails at once with the message.
  - An `htp://` URI fails at once with the `ValueError`.
  - A refused import after a lost connection fails the call at once.
  - A refused import does not count in the attempts of a later INFO message.
- **Server unit tests:** `tests/server/test_runner.py` and `tests/server/test_endpoint.py` expect `-32002` instead of `-32603`, also for an import.
- **Robot tests** in `atests/connection/connect_retry.robot`, with a window of 30 seconds against the suite's own server:
  - an import of a library that the server does not serve;
  - an import of `MissingDependencyLib`, which fails to import on the server.

  Both fail within a few seconds with the server's message. The suite's server also serves `MissingDependencyLib`.
- **No Robot test for a stopping server.** The time between the start of a stop and the closed listener is too short to reach reliably. The client unit test and the runner unit tests cover the two halves.

## Risks / Trade-offs

- [A failure that a later attempt could have fixed is now reported at once, such as an import that fails because a file on the server appears later] → The server answered, so that is no connection problem. Without retry it fails the same way, and the next session tries again.
- [Another server sends `-32603` while it stops] → Its import fails at once, as without retry. The protocol reference names `SHUTTING_DOWN` for a stopping server.
- [Changing `_shutting_down()` changes the code that clients see for keyword calls during a stop] → The client shows only the message. No compatibility with older versions in pre-alpha.

## Migration Plan

Client, protocol and server change in one signed commit. Rollback is a revert of that commit.
