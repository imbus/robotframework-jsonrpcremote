# Proposal

## Why

The Robot suites in `tests/robot/` cover echo calls, type round trips, init arguments, variables, lost connections, connect retry, shutdown and stdio. Several everyday uses of the library are not tested end to end:

- the session scope `GLOBAL`, and the end of a `SUITE` session at the end of its suite;
- the server's allowlist: a rejected library, the default library when the client names none, and a server without an allowlist;
- call forms: `*args`, `**kwargs`, named-only and positional-only arguments, embedded arguments;
- Libdoc for a remote library: documentation, arguments, types and tags;
- Python objects that travel as pickles: `datetime`, `Decimal`, `set`, `bytes` and an instance of a custom class;
- Unicode and large payloads;
- forwarding of log levels and HTML messages;
- two library instances against the same server in one run, with their logs kept apart;
- the server's `--variablefile` option.

Later changes in the series rework exactly these areas: the library import, the scope of `GLOBAL` libraries and the encoding of values. These tests should exist before.

Found in the project review of 2026-10-27 (item TEST-6).

## What Changes

- **Tests:** new Robot tests and suites for the items above, with small helper libraries under `tests/robot/` where needed.
- **Not here:** tests that depend on other changes of the series. Skip, continuable and fatal failures and exact failure messages come with `fix-keyword-failure-reporting`, output of child processes over stdio with `fix-server-stdio-stdout`, and `GLOBAL` libraries shared between clients with `clarify-global-library-scope`. `[Timeout]` on a remote keyword needs a keyword timeout, which is not part of this series.
- **Bugs found:** a test that reveals a bug is skipped with a message that names the bug, and the bug gets a change of its own.
- No product code and no behavior change, so the change has no spec delta (`skip_specs: true`).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **Tests:** `tests/robot/`; a suite that needs a server of its own gets the next free fixed port after 8277.
- **CI:** the Robot step takes longer.
- **Code:** none.
- **Order:** before `fix-server-library-import`, `clarify-global-library-scope` and `encode-json-values-natively`, whose behavior these tests guard.
