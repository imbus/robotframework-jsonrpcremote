# Proposal

## Why

JSON-RPC error responses are hard to handle for callers, and they show server internals to every client:

- **One generic exception:** the peer turns an error response into a plain `Exception("RPC Error <code>: <message> (<data>)")`. Callers cannot tell `METHOD_NOT_FOUND`, `INVALID_PARAMS` or a server error apart without parsing the text. `packages/jsonrpcpeer/README.md` says that a handler can raise `JsonRpcError` to answer with a code, but that is a dataclass, not an exception.
- **Tracebacks for everyone:** the peer puts `traceback.format_exc()` into `data` of the error response for every exception in a handler and for invalid params, including absolute paths on the server. Its exception text contains `data`, so a Robot failure caused by a protocol error, such as a refused library import, contains the frames of the server's own code. The server itself logs nothing about these errors.
- **Unused error codes:** the protocol defines `NOT_INITIALIZED`, `KEYWORD_NOT_FOUND` and `ARGUMENT_MISMATCH`, but the server uses none of them. A call before `initialize` and a refused import are answered with `-32603 Internal error`.
- **Unknown keyword:** a keyword the library does not have fails with `list index out of range`. `find_keywords()` returns a list, so the check `if kws is None` never applies. This happens, for example, when the client's library definition is outdated after a server update. The message behind that check names the import token instead of the library.
- **Calls that do not run look like failed keywords:** `run_keyword` answers an unknown token, a server that is stopping and a return value that cannot be transferred with a `RunKeywordError`, as if the keyword had failed. `fix-keyword-failure-reporting` left these calls to this change.

Found in the project review of 2026-10-27 (items PEER-5, PROTO-4 and SERVER-7) and checked against the real server on 2026-11-01.

## What Changes

- **Peer:** an error response raises a new exception `JsonRpcResponseError` with the fields `code`, `message` and `data`, exported by `jsonrpcpeer`. A handler raises it to answer with that error.
- **Peer:** an error response carries a traceback in `data` only if the peer is configured to send it. By default it does not. The peer logs the traceback of an unexpected exception in a handler, so that it is not lost.
- **Server:**
  - answers a call before `initialize` with `NOT_INITIALIZED`;
  - answers a call of an unknown keyword with `KEYWORD_NOT_FOUND` and a message that names the keyword and the library's real name;
  - answers a refused import, of a library it does not serve or without a name it needs, with `INVALID_PARAMS`;
  - reports only a keyword that ran and failed with a `RunKeywordError`; every other call that it cannot complete gets a JSON-RPC error;
  - has an option that turns on tracebacks in error responses for debugging.
- **Protocol:** `ARGUMENT_MISMATCH` is removed.
- **Client:** fails the library import or the keyword call with the message of a protocol-level error only. `data`, marked with `[remote] `, goes to the log at DEBUG level under the keyword, like the traceback of a failed keyword; at a library import it follows the message, like the traceback of a local library.
- **Tests:** unit tests for the exception, for responses with and without traceback, for the error codes and for the client's message; a test with an outdated library definition calls a keyword the server no longer has; Robot tests for the messages of a refused import and of an unknown keyword.
- **Docs:** error handling in `packages/jsonrpcpeer/README.md`; on the documentation site, the section Errors and `RunKeywordError` on the protocol page, how protocol errors appear in Robot Framework in the guide Failures of remote keywords, and the new option in the server reference.

Decisions confirmed on 2026-11-01:

- `JsonRpcResponseError` is a subclass of `Exception` and separate from `JsonRpcConnectionClosedError`; its text keeps the form `RPC Error <code>: <message>`, without `data`.
- Tracebacks in error responses are switched on by a server option of their own, not by `--verbose`, because sending them is a decision about what clients may see.
- A `RunKeywordError` reports only a keyword that ran and failed. An unknown token, a server that is stopping and a return value that cannot be transferred become JSON-RPC errors, with the same message in Robot Framework.
- `ARGUMENT_MISMATCH` is removed: Robot Framework checks the arguments on the client, and an argument error on the server stays a keyword failure, like for a local keyword.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: adds requirements for the exception raised for an error response, for a handler that raises it, for tracebacks in error responses and for logging them.
- `server`: adds requirements for the error codes of a call before `initialize`, of an unknown keyword and of a refused import, that a `RunKeywordError` reports only a keyword that ran, and for the option that sends tracebacks.
- `client`: adds the requirement that a protocol-level error is reported with its message, without the data of the response.

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py` (sending and receiving error responses), `packages/jsonrpcpeer/src/jsonrpcpeer/__init__.py` (export); `packages/server/src/robot_jsonrpcremote_server/_endpoint.py` (`import_library`, `run_keyword`), `_runner.py` (`_robot_run_keyword`) and `__main__.py` (option); `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py` (`RobotJsonRpcErrorCode`); `src/JsonRpcRemote/__init__.py`.
- **Public API:** new exception `jsonrpcpeer.JsonRpcResponseError`, `jsonrpcpeer` also exports `JsonRpcErrorCode`, a peer option for tracebacks, a server CLI option.
- **Protocol:** uses the existing error codes and removes `ARGUMENT_MISMATCH`; no new fields.
- **Behavior:** error messages in Robot no longer contain the frames of the server's own code. A library that fails to import keeps Robot Framework's message, with the traceback of the library's code and `PYTHONPATH`, as for a local library.
- **Order:** after `fix-keyword-failure-reporting`, which changed the same code path in the client; before `fix-peer-message-handling`, which changes the peer's handling of failed notifications next to it.
