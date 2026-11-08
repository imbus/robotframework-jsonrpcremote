# Tasks

The tests go into `tests/test_server_cli.py`. A test that starts the server as a process uses `_run_server` there, with the environment from a new helper that copies `os.environ` without the `ROBOT_JSONRPC_*` variables and adds the ones the test sets. Every new test that covers a change is run against a copy of the server package without that part of the change, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the server processes that the tests start. Each task names what it takes out for that check.

The change adds no Robot test: it concerns the command line of the server before anything starts. A Robot run sees it only when the client starts a stdio server in such an environment, as a server that ends during its start, which the client reports as before.

## 1. Port from the environment

- [x] 1.1 In `build_arg_parser()`, give `--port` the string from `ROBOT_JSONRPC_PORT` as its default, or `str(DEFAULT_PORT)` without it, and keep `type=int` (design decision 1). Add these tests:
  - `test_invalid_port_from_the_environment_is_a_usage_error`: the server with `ROBOT_JSONRPC_PORT=abc` and the library `SomeLib` exits with code 2, and its stderr holds `--port` and `'abc'`, but neither `Traceback` nor `up and running`;
  - `test_port_from_the_environment_is_a_number`: with `ROBOT_JSONRPC_PORT=9001`, `build_arg_parser().parse_args(["Lib"]).port` is the integer `9001`, and without the variable it is `8271`;
  - `test_command_line_takes_precedence_over_an_invalid_environment`: with `ROBOT_JSONRPC_PORT=abc`, `parse_args(["--port", "9000", "Lib"])` gives the port `9000`.

  Verify that the first and the third test fail in a copy with `int(os.environ.get("ROBOT_JSONRPC_PORT", DEFAULT_PORT))` as the default, and the second in a copy without `type=int`.
- [x] 1.2 In `docs/src/content/docs/reference/server.mdx`, section Environment variables, add after the sentence on precedence: a value that the option does not take, such as a port that is not a number, ends the server with the usage error of the option and exit code 2, as on the command line. Verify the page against the behavior of 1.1.

## 2. Mode from the environment

- [x] 2.1 Add a constant with the modes `tcp`, `stdio` and `pipe` and a `type` function for `--mode` that returns a known mode and raises `argparse.ArgumentTypeError` with `invalid choice: '<value>' (choose from tcp, stdio, pipe)` for any other value (design decision 2). `--mode` keeps its `choices`, built from the constant. `run()` refuses only the mode `pipe`, with its message that it is not supported yet. Add these tests:
  - `test_unknown_mode_from_the_environment_is_a_usage_error`: the server with `ROBOT_JSONRPC_MODE=tpc` and `SomeLib` exits with code 2, and its stderr holds `--mode`, `'tpc'`, `tcp` and `stdio`, but neither `not supported yet` nor `Traceback`;
  - `test_unknown_mode_gives_the_same_error_from_both_sources`: the error line that `parse_args(["Lib"])` writes with `ROBOT_JSONRPC_MODE=tpc` equals the one that `parse_args(["--mode", "tpc", "Lib"])` writes without the variable, both read with `capsys`.

  Change `test_run_rejects_unsupported_mode`: besides `--pipe`, it runs `run()` with `ROBOT_JSONRPC_MODE=pipe` and no mode option, and for both it checks exit code 2 and `not supported yet` on stderr. Extend `test_command_line_takes_precedence_over_an_invalid_environment` with `ROBOT_JSONRPC_MODE=tpc` and `--stdio`: the mode is `stdio`.

  Verify the failures in these copies:
  - the two new tests, in a copy without the `type` function, where `run()` refuses `tpc` with the old message;
  - the changed `test_run_rejects_unsupported_mode`, in a copy whose `type` function refuses `pipe` as unknown;
  - the extended precedence test, in a copy that checks `ROBOT_JSONRPC_MODE` with the `type` function already in `build_arg_parser()`.
- [x] 2.2 Extend the sentence from 1.2 with an unknown mode as a second example. Verify the page against the behavior of 2.1.

## 3. Integration checks

- [x] 3.1 Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy`, and verify that they pass.
- [x] 3.2 Run `uv run --all-packages pytest` and `uv run --all-packages robotcode run`, and verify that all unit tests and all Robot suites pass.
- [x] 3.3 Run `npm run build` in `docs/` and verify that the site builds without broken links.

## Workflow follow-up

- Commit the plan as `docs(openspec): plan fix-server-environment-values`, together with the removal of `openspec/changes/harden-server-network-defaults/`.
- After the implementation, check CI, including the Windows and the minimum Robot Framework jobs, then archive the change.
