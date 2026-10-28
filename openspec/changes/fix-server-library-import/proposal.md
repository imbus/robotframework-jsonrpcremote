# Proposal

## Why

Three defects affect importing a library on the server:

- **A default that cannot be pickled fails the whole import.** The server sends every argument default through `value_to_jsonable`, which pickles everything except JSON scalars. A single keyword whose default is a lambda, a lock, an open file or an instance of a local class makes the import fail: `RPC Error -32603: Can't pickle <function LambdaDefaultLib.<lambda> ...>`.
- **The library's name is the import token.** The server imports each library with its unique token as alias and reports `lib.name`, so the client receives the token, made of the library name, an endpoint ID and a counter, instead of the library name. The client works around this by ignoring the name when it compares definitions after a reconnect.
- **A library imported for a client that is gone stays loaded.** If a client disconnects while its `import_library` is still running, the server finalizes the client's libraries before the new token is registered. The import then completes, the token is added to the endpoint of the gone client, and the library instance stays in Robot's keyword store until the server ends. This is derived from the code and not reproduced yet. Connect retry makes it more likely: a client whose handshake exceeds `rpc_timeout` disconnects and tries again.

Found in the project review of 2026-10-27 (items SERVER-8, SERVER-10 and SERVER-6).

## What Changes

- **Defaults:** the server transfers each argument default on its own. A default that cannot be transferred is sent as its `repr()` string, and the import succeeds. The keyword still runs with its real default on the server.
- **Name:** the library definition carries the library's name, not the token.
- **Disconnect:** a library whose import completes after its client is gone is finalized right away.
- **Tests:** unit tests with the fixture from `add-server-runner-tests`; a Robot test imports a library with a lambda default and calls the keyword without that argument.

Assumptions recorded for review:

- The client never sends a default back to the server; Robot Framework only uses the defaults that `get_keyword_arguments` reports for documentation and argument conversion. The design verifies this before relying on it.
- Nothing depends on the token as the library name; the design checks the client and Libdoc output. The client keeps ignoring the name when it compares definitions, so it still works with older servers.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds requirements for argument defaults that cannot be transferred, for the library name in the definition, and for an import that completes after its client is gone.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/_runner.py` (`_robot_import_library`), `_endpoint.py` (`import_library`).
- **Protocol:** unchanged. `LibraryDefinition.name` now carries the library name, and a default that cannot be transferred arrives as a string.
- **Client:** no code change expected.
- **Order:** after `add-server-runner-tests` and `add-robot-integration-tests`; before `clarify-global-library-scope`, which touches the same import path.
