# Tasks

Every new test is run once against the code without the part of the change it covers, and must fail there.

## 1. Peer

No Robot test in this group: the peer shows in Robot Framework only through the client, which group 3 tests.

- [x] 1.1 In `peer.py`, add `JsonRpcResponseError(code, message, data=None)` with the text `RPC Error <code>: <message>`, and raise it for an error response, for an `error` that is not an object and for a response with neither `result` nor `error`. `jsonrpcpeer` exports it and `JsonRpcErrorCode` (design decision 1). Verify with tests in `tests/test_peer.py` for the `jsonrpc-peer` scenarios:
  - Response with code, message and data;
  - Error response is no connection failure;
  - Error is part of the package API;
  - Error that is not an object;
  - Response with neither a result nor an error.
- [x] 1.2 A request handler that raises `JsonRpcResponseError` answers with its code, message and data, and the peer does not log it (design decision 1). Verify with tests in `tests/test_peer.py` for the scenarios Handler raises an error with a code and Handler raises an error with data.
- [x] 1.3 Add the option `send_tracebacks=False` to `JsonRpcPeer`: every error response built from an exception gets the traceback in `data` only with it. The peer logs an unexpected exception of a request or notification handler with `logger.exception`, naming the method (design decision 2). Verify with tests in `tests/test_peer.py`, with `caplog` for the logging, for the scenarios:
  - Handler raises an unexpected exception;
  - Params cannot be converted;
  - Message cannot be parsed;
  - Peer is configured to send tracebacks;
  - Handler's own error stays as it is;
  - Request handler raises;
  - Notification handler raises.
- [x] 1.4 Rewrite the section Error Handling of `packages/jsonrpcpeer/README.md`: `JsonRpcResponseError` for a request that gets an error and for a handler that answers with one, with `code`, `message`, `data` and `JsonRpcErrorCode`; the option `send_tracebacks`; the logging (design decision 8). Verify that its code example runs as written in a scratch script against a pair of peers.

## 2. Protocol and server

The Robot tests of this behavior follow in 3.2, once the client reports the errors.

- [x] 2.1 Remove `ARGUMENT_MISMATCH` from `RobotJsonRpcErrorCode`. Verify with a test in `tests/test_protocol.py` that names the remaining codes with their values, `NOT_INITIALIZED` (`-32000`) and `KEYWORD_NOT_FOUND` (`-32001`), and with `grep` that nothing mentions the removed one outside `openspec/`, once 2.6 is done.
- [x] 2.2 In `_endpoint.py`, `import_library` and `run_keyword` raise `JsonRpcResponseError` with `NOT_INITIALIZED` before the handshake, and `import_library` with `INVALID_PARAMS` for a library it does not serve and for an empty name without a default library (design decision 3). Verify with:
  - tests in `tests/test_endpoint.py` for each case;
  - tests in `tests/test_server_end_to_end.py` against the real server for the scenarios Keyword call before the handshake, Library import before the end of the handshake, Library that the server does not serve and Import without a name. The server's stderr goes to a file, and the test for "logs no error" checks that the message is not in it.
- [x] 2.3 In `_runner.py`, `_robot_run_keyword` raises `JsonRpcResponseError` with `KEYWORD_NOT_FOUND` for an empty result of `find_keywords`, its messages about keywords use `lib.real_name`, and `_shutting_down()` returns a `JsonRpcResponseError` with `INTERNAL_ERROR` and the message `server is shutting down` (design decision 3). Verify with:
  - the scenario Keyword does not exist in `tests/test_server_end_to_end.py`;
  - the existing tests in `tests/test_runner.py` for a stopping server, adapted to the new exception, and a test in `tests/test_endpoint.py` that the error passes through `run_keyword`, for the scenario Server is stopping.
- [x] 2.4 `RobotServerEndpoint.run_keyword` catches only `KeywordFailedError` (design decision 4). Verify with:
  - a test in `tests/test_endpoint.py` that another exception leaves `run_keyword`; it replaces the test for the old answer;
  - tests in `tests/test_server_end_to_end.py` for the scenarios Unknown library token, Return value that cannot be transferred, Wrong number of arguments, Library with a missing dependency and Library whose initialization fails.
- [x] 2.5 Add the option `--send-tracebacks` and pass it from `run()` through `run_server`, `run_server_async` and the transport functions to the `JsonRpcPeer` in `handle_client` (design decision 6). Verify with:
  - a parser test in `tests/test_server_cli.py`;
  - `tests/test_server_stdio.py`, adapted to the new signature;
  - tests in `tests/test_server_end_to_end.py` for the scenarios Server without the option and Server with the option, with a second server that has the option and no libraries; its stderr goes to a file, for what it logs.
- [x] 2.6 Documentation (design decision 8):
  - **The protocol page** says in its section Errors which code answers what, `RunKeywordError` no longer mentions a call that does not run, and `ARGUMENT_MISMATCH` is gone.
  - **The server reference** lists `--send-tracebacks`, says that it shows the server's code and paths to every client, and says that the server logs unexpected errors with their traceback.

  Verify with `npm run build` in `docs/`, and review the behavior of 2.2 to 2.5 against the pages.

## 3. Client

- [x] 3.1 In `src/JsonRpcRemote/__init__.py`, turn `JsonRpcResponseError` into `RemoteError` through `_keyword_failure`, with the message and `str(data)` as the traceback, in `JsonRpcRemote.run_keyword` and in `_start_session` (design decision 5). Verify with tests in `tests/test_client_failures.py` on the fake server, looking at the exception as Robot's status reporter does, for the `client` scenarios:
  - Unknown keyword;
  - Data of the error;
  - Refused library import;
  - Data of the error at a library import;
  - Refused import when a later session starts.

  Also cover `data` that is not a string, and an error without `data`, which gives no details.
- [x] 3.2 Robot tests in a new suite `atests/protocol_errors.robot` with its own server on port 8281, a new library `atests/ProtocolErrorsLib.py` with a keyword whose return value cannot be pickled, `atests/MissingDependencyLib.py`, and `atests/VersionedLib.py`, a dynamic library that offers a keyword only if the server's variable `LIB_VERSION` is `before`. `ServerControl.start_jsonrpc_server` gets the argument `send_tracebacks`. The tests of an import read the execution error of a nested suite, `atests/_nested/failing_import.robot`, which stays complete. The suite checks:
  - a refused import fails with `failed: Library 'OtherLibrary' is not available.`, without `RPC Error` and without a traceback;
  - a library that fails to import shows the missing module and `PYTHONPATH`, without `RPC Error` and without the server's `peer.py` and `_endpoint.py`;
  - an outdated library definition: with `rpc_scope=TEST`, a test calls the keyword, the next test restarts the server with `LIB_VERSION:after`, the call fails with exactly `Keyword 'Removed Later' not found in library 'VersionedLib'.`, and the next call of another keyword returns its result;
  - with `--send-tracebacks` and `Set Log Level    DEBUG`, a call of the keyword whose return value cannot be pickled fails with the message, and the log holds `[remote] Traceback (most recent call last):`.
- [x] 3.3 Documentation (design decision 8): the guide `docs/src/content/docs/guides/failures.mdx` gets a section on errors that are not failures of a keyword: a refused import, a keyword the library no longer has, a stopping server and a library that fails to import, each with its message. `docs/examples/failures/` gets a suite `refused_import.robot`, and its `run.sh` checks the execution error with Robot's result API. Verify with `uv run --all-packages bash docs/examples/failures/run.sh` and `npm run build` in `docs/`.

## 4. Example server

- [x] 4.1 `examples/simple-robot-jsonrpcserver` answers with `NOT_INITIALIZED` before the handshake and with `KEYWORD_NOT_FOUND` for an unknown keyword, instead of an `Exception` and a `RunKeywordError`, because the protocol page shows it as a model (design decision 8). Verify with tests in `tests/test_example_server.py` for both codes and with `uv run --all-packages bash docs/examples/own-server/run.sh`.

## 5. Integration checks

- [x] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 5.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [x] 5.3 Run `npm ci` and `npm run build` in `docs/` and every `docs/examples/*/run.sh` with `uv run --all-packages bash`; verify all pass
- [x] 5.4 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`):
  - **Subject:** `fix: answer protocol errors with error codes and without server tracebacks`.
  - **Body:** explains `JsonRpcResponseError`, that tracebacks stay in the server's log unless `--send-tracebacks` is given, the codes and the rule for `RunKeywordError`, the client's message, and that `ARGUMENT_MISMATCH` is removed.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive` and sync its delta specs into `openspec/specs/jsonrpc-peer`, `openspec/specs/server` and `openspec/specs/client`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-rpc-error-responses`.
- Set PEER-5 and SERVER-7 to done in `playground/anforderungen-und-ideen.md`, note in PROTO-4 that the codes are done and the naming is not, and note in CLIENT-11 that a fix can now stop on `JsonRpcResponseError`.
