# Design

## Context

See proposal.md for the motivation and the decisions confirmed on 2026-11-01, and the delta specs of `jsonrpc-peer`, `server` and `client` for the behavior.

**Today, checked against the real server on 2026-11-01:**

| A client sends                              | The response                                                  | The server logs |
| ------------------------------------------- | ------------------------------------------------------------- | --------------- |
| a request before `robot/initialize`         | `-32603` with a traceback in `data`                           | nothing         |
| an import of a library it does not serve    | `-32603` with a traceback in `data`                           | nothing         |
| an import of a library that fails to import | `-32603`, Robot's message in `message`, a traceback in `data` | nothing         |
| params that cannot be converted             | `-32602` with a traceback in `data`                           | nothing         |
| an unknown method                           | `-32601` without `data`                                       | nothing         |
| an unknown keyword                          | `RunKeywordError`: `list index out of range`                  | an ERROR        |
| an unknown library token                    | `RunKeywordError`: `No library 'nope' found.`                 | an ERROR        |
| a keyword with a return value it cannot pickle | `RunKeywordError`: `Can't get local object …`              | an ERROR        |
| a keyword with too few arguments            | `RunKeywordError` of type `DataError`: Robot's message        | at DEBUG        |

**Other facts that shape the design:**

- **Exception names in Robot:** Robot Framework shows the name of an exception in front of its message, unless the name is generic. A plain `Exception` hides its name today; a class of our own would not.
- **Failed imports in Robot:** for a library whose `__init__` raises, Robot Framework builds `failed: {message}\n{details}`, in 7.2 and 7.5 alike. For a `RobotError`, `details` is its `details` attribute, so `RemoteError` keeps the client's own traceback out of the error.
- **Robot's message of a failed library import** holds the traceback of the library's code and the module search path. It arrives in `message`, without frames of the server's own code; those come only with `data`.
- **The library name:** the server imports each library with its token as alias, so `lib.name` is the token and `lib.real_name` the name of the library, in 7.2 and 7.5 alike.
- **`jsonrpcpeer` exports no error codes:** `JsonRpcErrorCode` lives in `jsonrpcpeer.peer` and is not exported.

## Goals / Non-Goals

**Goals:**

- One rule on the protocol: a `RunKeywordError` for a keyword that ran and failed, a JSON-RPC error for everything else. That is what the protocol page already says.
- Callers of the peer tell errors apart by their code instead of parsing text.
- A traceback of the server's own code goes to the server's log, and to a client only if the server's operator asks for it.

**Non-Goals:**

- **Responses to notifications:** they only lose the traceback here; `fix-peer-message-handling` removes them.
- **Connect retry for a refused import (CLIENT-11):** the client keeps repeating it. A later fix can now stop on `JsonRpcResponseError`.
- **New error codes:** a library that fails to import and an unknown token stay `INTERNAL_ERROR`. Nothing reads a more specific code today.
- **The token in messages that Robot Framework formats,** such as that of a wrong number of arguments: `fix-server-library-import` handles the library name.

## Decisions

### 1. One exception for both directions of an error response

`JsonRpcResponseError(code, message, data=None)` is an `Exception` with these fields and the text `RPC Error <code>: <message>`. The peer raises it for an error response, also for an `error` that is not an object and for a response with neither `result` nor `error`, which raise a plain `Exception` today. A request handler raises it to answer with that error, which is what the README promises of `JsonRpcError`. `jsonrpcpeer` exports it together with `JsonRpcErrorCode`, because callers need the codes to compare and raise them.

- **Alternative:** a separate exception for handlers to raise. It would hold the same three fields, and a handler that calls another peer could not pass an error on.
- **Alternative:** make the dataclass `JsonRpcError` raisable. It is the message on the wire, with `slots` and keyword-only fields; mixing it with `Exception` gains nothing.

### 2. The peer sends a traceback only with an option, and logs what it would have sent

- **Option:** `JsonRpcPeer(..., send_tracebacks=False)`. All places that put `traceback.format_exc()` into `data` today call one small method that returns it only with the option.
- **Logging:** when a request or notification handler raises anything but `JsonRpcResponseError`, the peer logs it with `logger.exception`, naming the method. Without this, the traceback would be lost, because the peer logs nothing today.
- **Not logged:** a `JsonRpcResponseError`, params that cannot be converted and a message that cannot be parsed. They say something about the request, not about a bug on this side.

- **Alternative:** log in the server's endpoint instead of the peer. Every handler would need it, and a notification handler or another user of the peer would still lose the traceback.

### 3. The server raises what it expects, with a code

| Case                                        | Error                                | Raised in                     | Logged at ERROR |
| ------------------------------------------- | ------------------------------------ | ----------------------------- | --------------- |
| before the handshake                        | `NOT_INITIALIZED`                    | endpoint                      | no              |
| unknown keyword                             | `KEYWORD_NOT_FOUND`                  | runner, with `if not kws`     | no              |
| refused import, or no name without a default | `INVALID_PARAMS`                    | endpoint                      | no              |
| server is stopping                          | `INTERNAL_ERROR`, `server is shutting down` | runner, `_shutting_down()` | no              |
| any other exception, such as an unknown token or a library that fails to import | `INTERNAL_ERROR`, with its message | peer | yes             |

The messages about keywords in `_robot_run_keyword` use `lib.real_name`. A stopping server is expected, so it raises `JsonRpcResponseError` too and does not log a traceback for each call it rejects; it needs no code of its own, since no caller acts on it.

A library that fails to import stays with the last row: a missing dependency on the server is what its operator should see.

### 4. `run_keyword` catches only the failure of a keyword

`RobotServerEndpoint.run_keyword` keeps `except KeywordFailedError` and drops `except Exception`. Everything else reaches the peer, which answers with a JSON-RPC error and logs it. This also removes the endpoint's own `logger.exception`.

An argument error on the server stays a keyword failure: Robot's runner reports it as `ExecutionFailed`, so it takes the path of `fix-keyword-failure-reporting`.

### 5. The client reports a protocol-level error like a failed keyword

A function turns `JsonRpcResponseError` into `RemoteError`, through `_keyword_failure` with the message and `str(data)` as the traceback, so `data` gets the mark `[remote] ` and an error without `data` has no details. Robot Framework then does the rest, as for a failed keyword:

- **keyword call:** the failure has exactly the message, and `data` goes to the log at DEBUG under the keyword;
- **library import:** the import error reads `failed: <message>`, and `data` follows it, as Robot Framework shows the traceback of a local library. A DEBUG message at that moment would not appear in the log.

The conversion happens in two places: `JsonRpcRemote.run_keyword` for the keyword call and `_start_session` for every start of a session, which covers the library import and a later session.

With connect retry, the error stays a `JsonRpcResponseError` in `_connect_with_retry`. A window that passes gives the `ConnectionError` of today, with `_describe_error` naming it as the last error.

- **Alternative:** give `JsonRpcResponseError` the attribute `ROBOT_SUPPRESS_NAME`. Robot Framework would hide the name, but it would still log the client's asyncio frames as the traceback, and `jsonrpcpeer` knows nothing of Robot Framework.
- **Alternative:** raise an error of Robot's public API. As in `fix-keyword-failure-reporting`, they do not replace the client's own traceback.

### 6. `--send-tracebacks` travels like `--verbose`

The option goes from `run()` through `run_server`, `run_server_async` and the transport functions to `handle_client`, which passes it to the `JsonRpcPeer` of each connection. That is how `verbose` travels, and all connections of a server behave alike. It has no environment variable, since `--verbose` has none and it is meant for a debugging session.

- **Alternative:** an attribute of `RobotRemoteContext`, with fewer signatures to change. That object holds the settings of the Robot execution, not of the connections.

### 7. Tests

- **Unit tests:**
  - `tests/test_peer.py`: the exception and its text, the next request after an error, an `error` that is not an object, a response without `result` and `error`, a handler that raises it with and without data, no `data` by default, with the option, and the logging with `caplog`;
  - `tests/test_endpoint.py`: `NOT_INITIALIZED`, `INVALID_PARAMS`, and that another exception leaves `run_keyword`; this replaces the test of `fix-keyword-failure-reporting` for the old answer;
  - `tests/test_runner.py`: `server is shutting down` as `JsonRpcResponseError`;
  - `tests/test_client_failures.py`: the message, `data`, a normal failure, the library import and a later session;
  - `tests/test_server_cli.py`: the parser takes `--send-tracebacks`.
- **The real server over the protocol** (`tests/test_server_end_to_end.py`): every scenario of the `server` delta spec, including the module search path of a failed import, a return value that cannot be pickled and a wrong number of arguments. A second server runs with `--send-tracebacks`, and both write their stderr to a file, for what they log.
- **Robot tests:** a new suite `atests/protocol_errors.robot` with its own server on port 8281:
  - a refused import shows the message, without `RPC Error` and without a traceback. The tests of an import run a nested suite `atests/_nested/failing_import.robot` and read its execution error, because Robot Framework removes the middle of a long error of the keyword `Import Library`, which would hide what the tests look for;
  - an outdated library definition: with `rpc_scope=TEST`, the suite restarts the server with a variable that makes a dynamic library offer fewer keywords, because Robot Framework caches a library's keywords per name and arguments for the life of the server process. The next test calls the keyword that is gone and expects the exact message.
- **The example server:** `tests/test_example_server.py` checks its two codes.

### 8. The documentation and the example server

- **Protocol page:** the section Errors says which code answers what, and `RunKeywordError` no longer mentions a call that does not run. `ARGUMENT_MISMATCH` goes away.
- **Guide "Failures of remote keywords":** a section on errors that are not failures of a keyword: a refused import, a keyword the library no longer has, a stopping server, and a library that fails to import. `docs/examples/failures/` gets a small suite that imports a library the server does not serve, and its `run.sh` checks the execution error.
- **Server reference:** `--send-tracebacks`, and that the server logs unexpected errors.
- **`packages/jsonrpcpeer/README.md`:** the section Error Handling describes `JsonRpcResponseError` in both directions, the option and the logging.
- **The example server:** the protocol page shows it as a model, so it answers with `NOT_INITIALIZED` and `KEYWORD_NOT_FOUND` too.
- **Status and roadmap:** names nothing of this, so it stays as it is.

## Risks / Trade-offs

- **[A failed library import logs a traceback at ERROR on the server]** Over stdio, this also appears on the console of `robot`, beside Robot's clean error. → It is rare and worth seeing, and `fix-keyword-failure-reporting` already keeps failing keywords off that console.
- **[The message of a failed library import shows paths of the server]** Robot's message holds the library's traceback and the module search path, with or without `--send-tracebacks`. → The test author needs them, as for a local library, and they contain no frames of the server's own code.
- **[`--send-tracebacks` shows the server's code and paths to every client]** → It is off by default and named for what it does; the server reference says so.
- **[An exception without a message answers with an empty message]** Robot Framework would then show the name `RemoteError`. → Unchanged from today in substance, and the traceback is in the server's log.
