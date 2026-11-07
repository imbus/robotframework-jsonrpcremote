# Tasks

Every new test is run once against the code without the part of the change it covers, and must fail there. A keyword call over a broken stdio connection hangs, because no keyword timeout exists, so these checks run under `timeout`.

## 1. The function in `jsonrpcpeer`

- [ ] 1.1 Create `packages/jsonrpcpeer/src/jsonrpcpeer/stdio.py` with `open_stdio_connection()`, the checks of stdin and stdout, and the move of the standard streams (design decisions 2 to 4), with `_check_stdin()` taken over from the server with its messages unchanged. On Windows it raises the error named in design decision 6. Export the function in `__init__.py`. Verify with the new `tests/test_stdio_connection.py`, which runs each scenario in a process of its own (design decision 7), with `skipif(win32)`:
  - **Requirement A process can connect over its stdin and stdout:** A peer answers a request, Large messages.
  - **Requirement What is written to stdout appears on stderr:** print (the parent reads the line from stderr while the process still runs), Direct write to file descriptor 1, Child process (`subprocess` and `os.system()`), Text buffered before the call, After the connection has closed.
  - **Requirement stdin no longer delivers the data of the connection:** Reading stdin in the process, Reading stdin in a child process.
  - **Requirement A child process does not keep the connection open:** Process ends while a child process runs. The process starts a child with a limit of 15 seconds, and the test requires the end of the stream within 10.
  - **Requirement The connection is refused if stdin or stdout cannot be used:** all six scenarios.
  - **Requirement A closed stderr does not get in the way of the connection:** Process without a stderr.

  This adds no Robot test for the function itself, because Robot Framework sees it only through the server and the example server, which 2.2 and 3.2 cover.
- [ ] 1.2 Add `_WritePipeProtocol` to `stdio.py` and use it for the pair (design decision 5). Remove the comment in `peer.py` that names the stdio pipe as an example of a writer that raises from `wait_closed()`. Verify in `tests/test_stdio_connection.py` with the three scenarios of the requirement The pair from stdin and stdout closes like the pair of a socket. For The other end goes away, the process runs with `-X dev`, and the test requires that its stderr has no `never retrieved`, `ResourceWarning` or `unclosed`.

## 2. The server

- [ ] 2.1 In `packages/server/src/robot_jsonrpcremote_server/__main__.py`, make `run_stdio_server()` call `open_stdio_connection()`, and remove `_stdio_streams()`, `_check_stdio_stdin()` and the imports that only they use (design decision 6). In `tests/test_server_stdio.py`, patch `server_main.open_stdio_connection` in the tests with a fake pair, point the Windows tests at the new function, and remove `test_stdio_streams_reject_a_stdin_that_cannot_be_watched` and `test_stdio_streams_connect_a_pipe`, because 1.1 covers them. In `atests/ConnectionLossLib.py` and `atests/StdioEchoLib.py`, remove from the docstrings the reason that a library must not write to stdout over stdio. Verify that `tests/test_server_stdio.py`, `tests/test_server_cli.py` and the suites `atests/stdio_*.robot` still pass, unchanged except for this. This task adds no Robot test, because it moves code and changes no behavior.
- [ ] 2.2 Add the Robot tests (design decision 7):
  - **New library:** `atests/StdioOutputLib.py`, with a variable for its server command in `atests/stdio_vars.py`.
  - **New suite:** `atests/stdio_output.robot` with `rpc_scope=TEST` and the tag `posix`.
  - **Requirement In stdio mode only protocol messages reach the client:** the five scenarios; the test for print in a keyword checks the message with `atests/LogCapture.py`, as `atests/stdio_probe.robot` does.
  - **Requirement In stdio mode keywords see an empty stdin:** both scenarios.
  - **Requirement In stdio mode a child process does not hide the end of the server:** its scenario, with the times checked by `Get Time    epoch`.

  Against the code without the move of task 1.1, under `timeout`, each test except print in a keyword must fail or hang; print in a keyword passes there, because it holds today too.
- [ ] 2.3 In `tests/test_server_stdio.py`, add tests that run the real server with `StdioOutputLib`, stdin and stdout connected to a `JsonRpcPeer` and stderr captured, and check that the text of the scenarios Child process that writes to stdout, Direct write to file descriptor 1, Robot Framework's console output and Output after a keyword returned appears on stderr. A Robot test cannot see the stderr of the server.

## 3. The example server

- [ ] 3.1 In `examples/simple-robot-jsonrpcserver/src/simple_robot_jsonrpcserver/__main__.py`, add the option `--stdio` (design decision 6). Describe it in the README of the example, under Run it and What it demonstrates. Verify with a new test in `tests/test_example_server.py` that starts `python -m simple_robot_jsonrpcserver --stdio` and runs a whole session over its stdin and stdout, with the output of its `print()` calls on stderr.
- [ ] 3.2 Add `atests/stdio_own_server.robot` with the tag `posix` and a variable for the command in `atests/stdio_vars.py`: Echo with umlauts, a message of 20,000 characters and 100 calls (design decision 7). Against the code without the move of task 1.1, under `timeout`, the suite must fail or hang from the message of 20,000 characters on.

## 4. CI

- [ ] 4.1 In `.github/workflows/ci.yml`, add `"3.14t"` to `python` in the job `test`, and the step Check that the GIL is off after Sync dependencies (design decision 8). Verify locally on a copy of the tree with `UV_PYTHON=3.14t` and `UV_PROJECT_ENVIRONMENT` in the scratchpad: `uv sync --all-packages`, the command of the step, `uv run --all-packages pytest` and `uv run --all-packages robotcode run` pass, and with `PYTHON_GIL=1` the command of the step exits with 1. CI itself is the check for macOS (Workflow follow-up). It adds no test, because it adds no behavior.

## 5. Documentation

- [ ] 5.1 In `docs/src/content/docs/guides/tcp-and-stdio.mdx`:
  - Remove the limit **stdout carries the messages**.
  - Under stdio, add that what a library prints during an import or a keyword is logged as usual, that all other output to stdout appears on the server's stderr, and so on the console of `robot`, and that a library or child process that reads stdin sees the end of its input.
  - Extend `docs/examples/stdio` with a keyword whose child process writes to stdout, and a test for it in `greet.robot`.

  Verify with `uv run --all-packages bash docs/examples/stdio/run.sh`. Review the page against `atests/stdio_output.robot`.
- [ ] 5.2 In `docs/src/content/docs/reference/protocol.mdx`, under Example: a hand-written server, describe `open_stdio_connection()` and `simple-robot-jsonrpcserver --stdio`, and say that output of the server appears on its stderr. Add `docs/examples/own-server/echo_stdio.robot`, shown on the page, and run it in `docs/examples/own-server/run.sh`. Verify with `uv run --all-packages bash docs/examples/own-server/run.sh`.
- [ ] 5.3 In `packages/jsonrpcpeer/README.md`, add a section on `open_stdio_connection()` under Usage, after Creating a Server, whose snippet serves an endpoint as the section Endpoints does. Name the function under Features, next to Flexible. Verify by running the snippet of the section in a process with pipes on its stdin and stdout, and sending it a request.
- [ ] 5.4 In `docs/src/content/docs/getting-started.mdx`, say next to the requirement for Python 3.12 that the client and the server also run on the free-threaded build of Python 3.14. In `docs/src/content/docs/roadmap.mdx`, under Available today, add `open_stdio_connection()` to the group Package `jsonrpcpeer`, limited to POSIX systems as on the guide. The roadmap names no Python versions, so the free-threaded build goes on Getting started only. Verify with `npm ci` and `npm run build` in `docs/`, which also check the internal links of 5.1 to 5.4.

## 6. Integration checks

- [ ] 6.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [ ] 6.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"`; verify all Robot suites pass.
- [ ] 6.3 Run the unit tests and all Robot suites with Python 3.14 and 3.15 by the recipe for several Python versions, and on the Windows VM; verify all pass. On Windows, the stdio tests stay excluded by the tag `posix`, and `atests/stdio_windows.robot` still passes.
- [ ] 6.4 Run `uv run --all-packages bash docs/examples/<name>/run.sh` for every example; verify all pass.
- [ ] 6.5 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`), staging only the paths of this change, because another session may work on `main`:
  - **Subject:** `feat(peer): connect a process over its stdin and stdout`.
  - **Body:** names the moved streams and why they cannot be left in place, the close behavior of the pair, the server and example server as users, and the CI job with 3.14t.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass, with the jobs for 3.14t on all three operating systems, and that the step Check that the GIL is off ran in them. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive` and sync its delta specs into `openspec/specs/jsonrpc-peer` and `openspec/specs/server`.
- Commit the archive as its own signed commit: `docs(openspec): archive add-stdio-streams`.
- In `playground/anforderungen-und-ideen.md`, set NET-6 to done and note the first piece of NET-5. In `playground/umsetzungsplan-review.md`, mark the entry that replaces change 13.
- Then start `add-windows-stdio`.
