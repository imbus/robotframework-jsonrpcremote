# Design

## Context

See proposal.md for the motivation. The current setup:

- pytest collects `tests/` in its default import mode, `prepend`. Without `__init__.py` files, pytest puts the folder of each test module at the front of `sys.path`. That is how the modules import the helpers `fake_server`, `connected_peers`, `value_types` and `server_over_pipes` by their names.
- mypy checks `tests` with `explicit_package_bases`, and `tests` is in `mypy_path`. A file in `tests/` is the module of its name, such as `fake_server`.
- `robot.toml` runs `atests` with `python-path = ["atests"]`. The client imports the types of the test libraries by their names from there, as the server does. The suites import their libraries and tools as `Library  Name.py` or `Variables  name.py`, and they give the server `pythonpath=${CURDIR}`.
- Robot Framework looks up a library or variable file given as a relative path in the folder of the suite first, and then in every folder of `sys.path` (`robot.utils.find_file`). Versions 7.2 and 7.5 do the same.
- Nested runs (`NestedRobot.py`) start `python -m robot` without a module search path.
- A few tests reach outside their folder by path. They point at helpers next to them, at the libraries in `atests/` that they start the server with, at `atests/ServerControl.py` or at the repository root.

## Goals / Non-Goals

**Goals:**

- Every test module and suite sits in a folder that names its package or topic. No test changes what it checks.
- A suite finds its libraries, tools and nested suites the same way in every folder.

**Non-Goals:**

- Splitting large test modules such as `test_peer.py` by topic. That can follow as a change of its own.
- Renaming test modules, test functions or Robot tests, or changing ports.
- Making single suites runnable without `robot.toml`. That already needs the module search path today.

## Decisions

### Unit tests: package folders, names kept, helpers in `tests/`

The modules move by package. The package is the one whose code the module tests: `jsonrpcpeer` for the peer, the JSON helpers and the stdio and pipe streams, `robot_jsonrpcremote_protocol`, `JsonRpcRemote`, or `robot_jsonrpcremote_server`.

| Folder | Modules |
|---|---|
| `tests/peer/` | `test_peer.py`, `test_typed_endpoints.py`, `test_json_helpers.py`, `test_json_helpers_nested.py`, `test_stdio_connection.py`, `test_pipe_connection.py` |
| `tests/protocol/` | `test_protocol.py`, `test_protocol_values.py` |
| `tests/client/` | `test_client_connection.py`, `test_client_connect_retry.py`, `test_client_failures.py`, `test_client_logging.py`, `test_client_session.py`, `test_client_values.py` |
| `tests/server/` | `test_endpoint.py`, `test_runner.py`, `test_server_cli.py`, `test_server_end_to_end.py`, `test_server_pipe.py`, `test_server_stdio.py` |
| `tests/examples/` | `test_example_server.py` |
| `tests/docs/` | `test_docs_examples.py` |
| `tests/atests/` | `test_server_control.py` |
| `tests/` | `test_packaging.py` and the helpers `fake_server.py`, `connected_peers.py`, `value_types.py`, `minimal_stdio_server.py`, `minimal_pipe_server.py`, `server_over_pipes.py`, `node_default_pipes.js` |

The folders get no `__init__.py`. The module names stay unique, so the `prepend` mode keeps working. pytest gets `pythonpath = ["tests"]` in `[tool.pytest.ini_options]`, so the helpers stay importable by their names. mypy needs no change: relative to `tests` in `mypy_path`, a moved module becomes a module of a namespace package, such as `client.test_client_session`, and the helpers keep their names. A probe on a copy collected the same 1204 tests and checked the same 53 files without errors.

Alternatives considered:

- Dropping the prefixes, as in `client/test_session.py`. That gives two `test_values.py` and two `test_stdio*.py`, so pytest would need `--import-mode=importlib`. Daniel chose to keep the names.
- Moving the helpers into `tests/helpers/` and putting that folder on both paths. mypy would then see each helper under two names (`helpers.fake_server` and `fake_server`) and stop with "Source file found twice".
- Using a `tests/conftest.py` only for its place on `sys.path`. `pythonpath` says what it does in the configuration.
- Moving `node_default_pipes.js` to `tests/peer/`, its only user. All helpers stay together, so a helper never has to move once a second user appears.

`test_packaging.py` checks every package, so it stays in `tests/`. A folder `tests/build/` would not work for it anyway, because `.gitignore` ignores every `build/`.

### Robot tests: folders by topic

The suites test features from end to end, not single packages, so their folders name topics:

| Folder | Suites |
|---|---|
| `keywords/` | `echo`, `argument_values`, `embedded_arguments`, `variables` |
| `values/` | `types`, `value_format`, `pickled_values`, `unicode_and_size` |
| `library/` | `default_library`, `init_args`, `init_kwargs`, `typed_init`, `library_path`, `no_allowlist`, `two_instances`, `rpc_scope`, `global_library`, `server_only_library`, `libdoc` |
| `logging/` | `log_forwarding`, `log_levels`, `log_outside_keyword_calls`, `console_messages` |
| `failures/` | `errors`, `failure_modes`, `protocol_errors`, `protocol_mistakes` |
| `connection/` | `session_start`, `lost_connection`, `connect_retry`, `connection_reset`, `shutdown`, `shutdown_with_clients` |
| `stdio/` | `echo`, `probe`, `output`, `scope`, `lost_connection`, `connect_retry`, `node_server`, `own_server` (each without `stdio_`) |
| `pipe/` | `echo`, `probe`, `output`, `scope`, `lost_connection`, `connect_retry`, `node_server`, `own_server`, `server` (each without `pipe_`) |

That covers all 50 suites. `__init__.robot` stays in `atests/`, so the shared server on port 8270 still starts once for all folders. `_nested/` stays as it is: several suites in different folders run the same nested suite, such as `failing_import.robot` from `connection/` and `failures/`. A folder starting with `_` holds no suites of the run.

### Libraries and tools: `libraries/` and `resources/`

`atests/libraries/` holds what a server or a suite runs as a library under test: `ArgumentValuesLib`, `CloseLogLib`, `ConnectionLossLib`, `ConsoleMessagesLib`, `FailureModesLib`, `GlobalCounterLib`, `LibdocLib`, `MissingDependencyLib`, `ProtocolErrorsLib`, `ServerProbeLib`, `SessionValueLib`, `StdioEchoLib`, `StdioOutputLib`, `SuiteCounterLib`, `TestCounterLib`, `TestScopedRemote` (a library built on the client), `TypedInitLib`, `TypedValuesLib`, `VersionedLib`, `typed_values_types.py`, `server_vars.py` (the variable file of the shared server), `node_keywords.js` and `node_keywords.cmd`. `atests/_server_only/` becomes `atests/libraries/server_only/`.

`atests/resources/` holds what only the suites use: `ServerControl`, `IsolatedServerControl`, `NestedRobot`, `LogCapture`, `LibdocSpecs`, `RawServerLib`, `ResetServer`, `stdio_vars.py`, `pipe_vars.py`, `typed_values_vars.py` and the new `paths.py`.

`robot.toml` sets `python-path = ["atests/libraries", "atests/resources"]`. The suites keep their imports such as `Library  ServerControl.py` and `Variables  stdio_vars.py`. Robot finds them on the module search path, and the client still imports the types of the test libraries by their names. The folders hold no suites, so Robot adds no suites for them. `libraries/server_only/` stays off the path of the client. The folder sits below a folder on the path, so `server_only` could only be imported as a package, and the type names on the wire, such as `ServerOnlyTypes.OnlyOnTheServer`, still do not resolve on the client.

Alternative considered: one folder for all Python files. That is one folder less, but the tools and the libraries under test would be mixed again. Daniel chose two folders.

### Paths from a variable file

`atests/resources/paths.py` is a variable file with `__all__ = ["LIBRARIES", "SERVER_ONLY", "NESTED"]`. It computes absolute paths from its own place. Without `__all__`, the imported `os` would become a variable `${os}` as well. Every suite that starts a server with libraries, imports a library by its path, or runs a nested suite imports `Variables  paths.py`, `__init__.robot` included:

- `pythonpath=${CURDIR}` becomes `pythonpath=${LIBRARIES}`, and `${CURDIR}${:}${CURDIR}${/}_server_only` becomes `${LIBRARIES}${:}${SERVER_ONLY}`.
- `${CURDIR}${/}_nested${/}…` becomes `${NESTED}${/}…`.
- `${CURDIR}${/}LibdocLib.py`, `${CURDIR}${/}ArgumentValuesLib.py` and `${CURDIR}${/}TestScopedRemote.py` become `${LIBRARIES}${/}…`, and `${CURDIR}${/}server_vars.py` becomes `${LIBRARIES}${/}server_vars.py`.

A value in the Variables section may use `${LIBRARIES}`, as `libdoc.robot`, `global_library.robot` and `server_only_library.robot` need. A probe passed on Robot Framework 7.2 and 7.5. `_nested/console_messages.robot` imports `${CURDIR}${/}..${/}libraries${/}ConsoleMessagesLib.py`, because nested runs have no module search path to find `paths.py`.

`stdio_vars.py` and `pipe_vars.py` move to `resources/`, but the server commands that they build need the libraries and the Node server. Their `_HERE` becomes a path to `libraries/`. The same holds for the paths into `atests/` in `tests/`: `server_over_pipes.py`, `test_server_stdio.py` and `test_client_connection.py` point at `atests/libraries`, and `test_server_control.py` at `atests/resources/ServerControl.py`.

Alternative considered: `${CURDIR}${/}..${/}libraries` in every suite. That ties each suite to its depth. A variable file names each folder once.

### Texts that name paths

Docstrings and suite documentation that name a moved file get its new path. These are `tests/client/test_client_connection.py`, `tests/atests/test_server_control.py`, `failure_modes.robot`, `global_library.robot`, `value_format.robot`, `ServerOnlyLib.py` and `node_keywords.cmd`. `AGENTS.md` and `CONTRIBUTING.md` get the new layout and commands. Archived OpenSpec changes keep their paths.

## Risks / Trade-offs

- [Robot runs the suites in a new order, folder by folder] → The tests are independent and the suites with servers of their own use ports of their own. A run with `--randomize suites` checks that the order does not matter.
- [`git log` and blame of a moved file need `--follow` or rename detection] → The moved files change only in a few path lines, so git still detects every move as a rename. The check is `git diff --cached -M --stat` before the commit.
- [A path missed in the move fails only on one platform, such as the `.cmd` wrapper or `${:}` on Windows] → The Windows VM runs pytest and all Robot suites before the commit.
- [Local run configurations and commands point at old paths] → `CONTRIBUTING.md` names the new commands.

## Migration Plan

The move lands in one signed commit, like the earlier `reorganize-test-directories`. Unit tests and Robot tests are moved one after the other, with the checks of each step before the next. Rollback is a revert of that commit.
