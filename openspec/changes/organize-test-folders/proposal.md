# Proposal

## Why

The tests have outgrown flat folders. `tests/` holds 24 test modules of four packages next to their helpers. `atests/` holds 50 suites, 31 Python files and a Node server with its wrapper script side by side, so a suite is hard to find among the libraries and tools around it, and nothing shows which package or topic a test covers. Folders by package and by topic make tests easier to find. They also tell a contributor where a new test belongs.

## What Changes

- **Unit tests:** `tests/` gets a folder per package: `peer/`, `protocol/`, `client/` and `server/`, plus `examples/` for the example server, `docs/` for the examples of the documentation site and `atests/` for the unit tests of the Robot tools. The test modules keep their names. The shared helpers (`fake_server.py`, `connected_peers.py`, `value_types.py`, the minimal servers, `server_over_pipes.py`, `node_default_pipes.js`) and `test_packaging.py`, which checks all packages, stay in `tests/`. pytest gets `pythonpath = ["tests"]`, so that the modules in the folders still import the helpers by their names.
- **Robot tests:** `atests/` gets a folder per topic: `keywords/`, `values/`, `library/`, `logging/`, `failures/`, `connection/`, `stdio/` and `pipe/`. In `stdio/` and `pipe/`, the suites lose their prefix, so `stdio_echo.robot` becomes `stdio/echo.robot`. `__init__.robot` and `_nested/` stay where they are.
- **Robot libraries and tools:** the Python and Node files move into two folders. `atests/libraries/` holds the libraries that the tests run, on a server or locally, with their types and the variable file of the shared server. `atests/libraries/server_only/` replaces `atests/_server_only/`. `atests/resources/` holds the tools of the suites: server control, nested runs, log capture, Libdoc specs, the raw and resetting servers and the variable files of the suites. Both folders go on the module search path of the Robot run in `robot.toml`, in place of `atests`.
- **Paths:** a new variable file `atests/resources/paths.py` gives the suites the folders `${LIBRARIES}`, `${SERVER_ONLY}` and `${NESTED}`. They replace `${CURDIR}` on the 38 lines of the suites where it points at a library or a nested suite, so that a suite works in any folder. The one nested suite that imports a library by its path gets the new relative path, because nested runs have no module search path.
- **Behavior:** nothing changes for the client, the server or the peer. Test names and ports stay. Only the long names of the Robot suites get their folder, such as `Atests.Stdio.Echo`, and Robot runs the suites in the order of the new folders.
- **Docs:** `AGENTS.md` and `CONTRIBUTING.md` describe the new layout and name the new paths.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ No spec-level behavior changes, so the change sets `skip_specs: true`.

## Impact

- **Tests:** every test module in `tests/` except `test_packaging.py` moves. Every suite, library and tool in `atests/` moves, except `__init__.robot` and `_nested/`. Paths to helpers, to `atests/` and to the repository root change in about a dozen places, among them the unit tests that start the server with a library from `atests/`.
- **Configuration:** `pyproject.toml` (pytest `pythonpath`) and `robot.toml` (`python-path`). CI, mypy and the VS Code settings name no path below `tests/` or `atests/` and need no change.
- **Docs:** `AGENTS.md` (orientation, task routing, common commands) and `CONTRIBUTING.md` (repository layout, running tests, the Hypothesis note, the documentation site).
- **Contributors:** local run configurations and commands that name a test file need the new path, such as `pytest tests/peer/test_peer.py`.
- Archived OpenSpec changes keep the old paths, because they record what was true then.
