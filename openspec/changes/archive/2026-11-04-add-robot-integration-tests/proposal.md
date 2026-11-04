# Proposal

## Why

The Robot suites in `atests/` cover echo calls, type round trips, init arguments, variables, lost connections, connect retry, shutdown, stdio, log levels, failure modes and a refused import. Several everyday uses of the library are not tested end to end:

- the session scope `GLOBAL`, which keeps its state across suites, and that the state of a `SUITE` session ends with its suite;
- the server's allowlist: the default library when the client names none, and a server without an allowlist;
- call forms: `*args`, `**kwargs`, named-only and positional-only arguments;
- Libdoc for a remote library: documentation, arguments, types and tags;
- Python objects that travel as pickles: `datetime`, `Decimal`, `set`, `bytes` and an instance of a custom class;
- Unicode and large payloads;
- forwarding of HTML messages;
- two library instances against the same server in one run, with their logs kept apart;
- the server's `--variablefile` option.

Later changes in the series rework exactly these areas: the library import, the scope of `GLOBAL` libraries and the encoding of values. These tests should exist before.

One small gap is in the code. The server sends the line of each keyword, but `get_keyword_source` of the client returns only the path. Robot's dynamic API also takes `path:lineno`, and with it the JSON and XML specs of Libdoc and listeners get the line, as for a local library.

Found in the project review of 2026-10-27 (items TEST-6 and CLIENT-16), and checked against a real server on 2026-11-03. Apart from the line, everything above worked in these probes, so the new tests are expected to pass. The two bugs that the probes found are fixed by `fix-server-argument-resolution`.

## What Changes

- **Tests:** new Robot tests and suites for the items above, with small helper libraries under `atests/` where needed. `ServerControl` gets an option for a variable file.
- **Line of a keyword:** `get_keyword_source` of the client returns `path:lineno` if the server reports a line. A Libdoc test covers it.
- **Not here:** values with backslashes or `${...}` and embedded arguments, whose tests come with `fix-server-argument-resolution`; output of child processes over stdio, with `add-stdio-streams`; `GLOBAL` libraries shared between clients, with `clarify-global-library-scope`. `[Timeout]` on a remote keyword needs a keyword timeout, which is not part of this series.
- **Bugs found:** a test that reveals a bug is skipped with a message that names the bug, and the bug gets a change of its own.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: the source of a keyword includes its line if the server reports one.

## Impact

- **Tests:** `atests/`; a suite that needs a server of its own gets the next free fixed port after 8283.
- **CI:** the Robot step takes longer.
- **Code:** `get_keyword_source` in `src/JsonRpcRemote/__init__.py`.
- **Docs:** the roadmap and the protocol page say that the source of a keyword comes with its line.
- **Order:** after `fix-server-argument-resolution`; before `fix-server-library-import`, `clarify-global-library-scope` and `encode-json-values-natively`, whose behavior these tests guard.
