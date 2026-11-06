# Proposal

## Why

Four defects affect importing a library, and the server grows with every import:

- **A default that cannot be pickled fails the whole import.** The server pickles every argument default that is not `null`, a string, a number or a boolean. A single keyword whose default is a lambda, a lock, an open file or an instance of a local class makes the import fail: `Can't pickle <function LambdaLib.<lambda> at 0x…>: attribute lookup LambdaLib.<lambda> on LambdaLib failed`.
- **A default whose class only the server has costs the keyword on the client.** The client unpickles the defaults when Robot Framework adds the keywords. If the library is installed only on the server, as in a container, an `Enum` default is enough: `Adding keyword 'Click' failed: … ModuleNotFoundError: No module named 'EnumLib'`, and the keyword is missing. Unpickling also runs code from the server on the client as soon as the library is imported.
- **The library's name is the import token.** The server imports each library under its token as alias and reports that alias, so the client receives `SlowLib_747d29b0_jsonrpc_0` instead of `SlowLib`. The client skips the name when it compares definitions after a reconnect.
- **A library imported for a client that is gone stays loaded.** If a client disconnects while its `import_library` still runs, the server finalizes the client's libraries before the new one is registered. The import then completes, and the instance stays in Robot's keyword store until the server ends. Reproduced on 2026-11-06: with an import of 1 s and a disconnect after 0.3 s, the library is never closed; with a disconnect after the import, it is closed once. A client disconnects during an import when the start of its session exceeds `rpc_timeout`, and with connect retry each attempt leaves one more instance; also when a Robot run is stopped during an import.
- **The server grows with every import.** Measured on 2026-11-06 with `tracemalloc` over 600 connections: 1045 bytes per connection stay in the server, most of them three messages that Robot Framework logs for each import (`Imported library class …`, `Found library … from cache`, `Imported library … with name …`) and keeps in its message cache. A `robot` run ends, the run of the server does not. This matters for a server that runs for a long time and serves many sessions.

Found in the project review of 2026-10-27 (SERVER-8, SERVER-10, SERVER-6), in the review of `add-documentation-site` (CLIENT-12, the part about defaults) and in the leak measurement of `fix-peer-lifecycle` (SERVER-12).

## What Changes

- **Defaults:** the server sends `null`, strings, numbers and booleans as they are, and every other default as text, as Libdoc shows it for a local library: `LEFT` for an `Enum` member, `[1, 2]` for a list, `<function MyLib.<lambda> at 0x…>` for a function. The import succeeds whatever the defaults are. The keyword still runs with its real default on the server, and the server converts the arguments with the real signature, for example `"[3, 4]"` to a list for a list default.
- **Defaults on the client:** the client hands the defaults to Robot Framework as they arrive and decodes no pickle in them. A library that is installed only on the server keeps all its keywords, and importing it runs no code from the server on the client.
- **Name:** the library definition carries the library's name, as Robot Framework reports it for an import without alias.
- **Reconnect:** the client also compares the name when it checks the definition after a reconnect, so it notices another library behind the same URI.
- **Disconnect:** a library whose import completes after its client is gone is finalized right away, also when the import completes while the server finalizes the client's other libraries.
- **Growth:** the server turns off Robot Framework's message cache once its run has started, as `rebot` does, so imports leave no messages behind.
- **Dead code:** the checks `if lib is None` after `get_library` in `_robot_import_library` and `_robot_run_keyword` go; Robot Framework raises an error itself when it finds no library.
- **Tests:** end-to-end tests with the real server in `tests/test_server_end_to_end.py`, unit tests for the endpoint and the client, and Robot tests. The Robot tests call a keyword with a lambda default and one with an `Enum` default of a library that only the server can import, each without that argument, and check that a call without an argument that has a default sends no value for it.
- **Docs:** the protocol reference (`LibraryDefinition.name`, `ArgumentDefinition.default`, which values travel as pickles, and what the server does when a connection ends without finalizing), the server reference on the conversion of arguments, the caution on pickles in the guide TCP and stdio, the check of the definition in the guide on lost connections, and the roadmap.

Assumptions recorded for review:

- Verified on 2026-11-06: the client never sends a default back to the server. Robot Framework fills in defaults only for a dynamic library whose `run_keyword` takes no named arguments, and the client's `run_keyword` takes them.
- Verified on 2026-11-06: nothing uses the token as the library name; only the comparison after a reconnect skips the name.
- Accepted: like Libdoc, the text of a default can contain a memory address, as for a function. After a reconnect to a restarted server, the client then reports a changed definition. This needs such a default and a restart of the server during a session.
- Not part of this change: a keyword that returns an object of a class that only the server has still fails on the client (the rest of CLIENT-12).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds requirements for the argument defaults and the name in the library definition, for an import that completes after its client is gone, and for a server that does not grow with each import.
- `client`: adds a requirement that defaults are used as they arrive, without decoding pickles; modifies the requirement on a changed library definition after a reconnect, which now includes the name.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/_runner.py` (`_robot_import_library`, `_robot_run_keyword`, the hook loop), `_endpoint.py` (`import_library` and the finalizing on disconnect); `src/JsonRpcRemote/__init__.py` (`get_keyword_arguments`, `_definition_changes`).
- **Protocol:** the fields stay. `LibraryDefinition.name` carries the library's name, and `ArgumentDefinition.default` is `null`, a string, a number, a boolean or the text of the default.
- **Security:** the client no longer unpickles anything when it imports a library; keyword arguments and return values still travel as pickles.
- **Order:** before `clarify-global-library-scope`, which touches the same import path, and before `encode-json-values-natively`, which then no longer needs to cover defaults.
