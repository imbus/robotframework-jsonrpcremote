# Proposal

## Why

JSON-RPC error responses are hard to handle for callers, and they show server internals to every client:

- **One generic exception:** the peer turns an error response into a plain `Exception("RPC Error <code>: <message> (<data>)")`. Callers cannot tell `METHOD_NOT_FOUND`, `INVALID_PARAMS` or a server error apart without parsing the text.
- **Tracebacks for everyone:** the peer puts `traceback.format_exc()` into `data` of every error response it sends, including absolute paths on the server. The client copies `data` into its message, so a Robot failure caused by a protocol error, such as a failed library import, contains the full server traceback.
- **Unused error codes:** the protocol defines `NOT_INITIALIZED`, `KEYWORD_NOT_FOUND` and `ARGUMENT_MISMATCH`, but the server uses none of them. A call before `initialize` is answered with `-32603 Internal error`.
- **Unknown keyword:** a keyword the library does not have fails with `list index out of range`. `find_keywords()` returns a list, so the check `if kws is None` never applies. This happens, for example, when the client's library definition is outdated after a server update.

Found in the project review of 2026-10-27 (items PEER-5, PROTO-4 and SERVER-7).

## What Changes

- **Peer:** an error response raises a new exception `JsonRpcResponseError` with the fields `code`, `message` and `data`, exported by `jsonrpcpeer`.
- **Peer:** an error response carries a traceback in `data` only if the peer is configured to send it. By default it does not.
- **Server:** answers a call before `initialize` with `NOT_INITIALIZED`, and a call of an unknown keyword with `KEYWORD_NOT_FOUND` and a message that names the keyword and the library. A server option turns on tracebacks in error responses for debugging.
- **Client:** reports a protocol-level error with its message only; `data` goes to the log at DEBUG level.
- **Tests:** unit tests for the exception, for responses with and without traceback, for both error codes and for the client's message; a test with an outdated library definition calls a keyword the server no longer has.
- **Docs:** error handling in `packages/jsonrpcpeer/README.md`; on the documentation site, how protocol errors appear in Robot Framework, and the new server option.

Assumptions recorded for review:

- `JsonRpcResponseError` is a subclass of `Exception` and separate from `JsonRpcConnectionClosedError`; its text keeps the form `RPC Error <code>: <message>`, without `data`.
- Tracebacks in error responses are switched on by a server option of their own, not by `--verbose`, because sending them is a decision about what clients may see.
- `ARGUMENT_MISMATCH` stays unused: Robot Framework checks the arguments on the client, and an argument error on the server stays a keyword failure, like for a local keyword.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: adds requirements for the exception raised for an error response and for tracebacks in error responses.
- `server`: adds requirements for the error codes of a call before `initialize` and of an unknown keyword, and for the option that sends tracebacks.
- `client`: adds the requirement that a protocol-level error is reported with its message, without the data of the response.

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py` (sending and receiving error responses), `packages/jsonrpcpeer/src/jsonrpcpeer/__init__.py` (export); `packages/server/src/robot_jsonrpcremote_server/_endpoint.py`, `_runner.py` (`_robot_run_keyword`) and `__main__.py` (option); `src/JsonRpcRemote/__init__.py`.
- **Public API:** new exception `jsonrpcpeer.JsonRpcResponseError`, a peer option for tracebacks, a server CLI option.
- **Protocol:** uses the existing error codes; no new fields.
- **Behavior:** error messages in Robot no longer contain server tracebacks.
- **Order:** after `fix-keyword-failure-reporting`, which changes the same code path in the client; before `fix-peer-message-handling`, which changes the peer's handling of failed notifications next to it.
