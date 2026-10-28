# Proposal

## Why

The server's integration with Robot Framework (`_runner.py`, `_endpoint.py`) is only tested end to end through the Robot suites. The unit tests replace Robot Framework completely: `test_runner.py` has two tests with fakes, and `test_endpoint.py` uses a stub context. So several paths run nowhere:

- the error paths of importing, running and finalizing: an unknown or ambiguous keyword, no Robot context, an unknown token;
- the allowlist rules of `import_library`: an empty name imports the first allowed library, a library outside the allowlist is rejected, and without an allowlist a name is required;
- the mapping of Robot log levels to protocol levels, and the filter that does not forward FAIL and SKIP messages or messages for a client that is gone.

Later changes in the series rework this code (`fix-server-library-import`, `clarify-global-library-scope`) and need a way to test it directly, without a server process.

Found in the project review of 2026-10-27 (item TEST-5).

## What Changes

- **Fixture:** a pytest fixture runs the server's Robot context (`RobotRemoteContext.run()`) in a background thread with a small test library, so unit tests can import libraries, run keywords and finalize libraries against the real Robot Framework.
- **Tests:** unit tests for the paths listed above, using the fixture.
- **Bugs found:** a test that reveals a bug is marked as an expected failure that names the bug, and the bug gets a change of its own.
- No product code and no behavior change, so the change has no spec delta (`skip_specs: true`).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **Tests:** a fixture module and new tests in `tests/unit/`; tests in `test_endpoint.py` that use the stub context move to the fixture where it covers the same ground.
- **Code:** none.
- **Order:** after `fix-rpc-error-responses`, which fixes the unknown-keyword path these tests cover; before `fix-server-library-import` and `clarify-global-library-scope`.
