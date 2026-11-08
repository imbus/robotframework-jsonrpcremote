# Tasks

Every new test is run once against the code without the part of the change it covers, and must fail there.

- **Time limits:** a call over a broken connection or a server that never connects can hang, so these checks and all runs on the Windows test VM have a hard time limit.
- **The VM:** Daniel starts it. When a task needs it, ask him and wait.
- **Bytecode:** copy no `__pycache__` to the VM.
- **Socket paths:** tests change into `tmp_path` and use relative names, or use a short directory from `tempfile.mkdtemp()`, because `tmp_path` can be too long for a socket path on macOS (design decision 11).

## 1. Pipes in `jsonrpcpeer`

- [x] 1.1 Add `packages/jsonrpcpeer/src/jsonrpcpeer/pipes.py` with `pipe_address()`, and with `open_pipe_connection()` and `start_pipe_server()` for POSIX, whose errors name the address. Export them from `__init__.py` (design decisions 3 and 4).
  - Verify in a new `tests/test_pipe_connection.py`:
    - **Requirement A pipe name means a named pipe on Windows and a socket file elsewhere:** Bare name on Windows and Empty name on every platform, with `sys.platform` patched for the Windows case; Relative path on other platforms.
    - **Requirement A process can listen on a pipe, and others can connect to it:** Messages in both directions, with a `JsonRpcPeer` on each side and a message of 1 MiB; Several connections; Nobody listens.
  - Counter-checks: against `pipe_address()` without the prefix, Bare name on Windows must fail. Against the functions without the address in their errors, Nobody listens must fail.
  - No Robot test: Robot Framework sees the functions only through the client and the server, which groups 2 and 3 cover.
- [x] 1.2 Add the Windows part to `_win32_pipes.py` and update its docstring (design decisions 2 and 4):
  - `open_pipe_connection()` with `create_pipe_connection()`;
  - `start_pipe_server()` with `start_serving_pipe()` and a subclass of `asyncio.AbstractServer` around its `PipeServer`;
  - the check for the proactor event loop.

  Verify on the Windows test VM that the tests of 1.1 pass. Add tests for Windows only:
  - **Requirement A pipe name means a named pipe on Windows and a socket file elsewhere:** Full name on Windows; A bare name never opens a file on Windows.
  - **Requirement A process can listen on a pipe, and others can connect to it:** An event loop without pipes on Windows, with `asyncio.SelectorEventLoop`.

  Counter-check: against `open_pipe_connection()` without `pipe_address()`, A bare name never opens a file must fail, because `CreateFile()` then opens the file. Also run `uv run mypy --platform win32`.
- [x] 1.3 Let `start_pipe_server()` refuse a name in use and remove its socket file when it is closed (design decision 5):
  - On Windows, it turns the `PermissionError` of `start_serving_pipe()` into an `OSError` with `errno.EADDRINUSE`.
  - On POSIX, it first connects to an existing socket file, and at `close()` it unlinks the file if it still has the inode that the server bound.

  Verify in `tests/test_pipe_connection.py`:
  - **Requirement A pipe server refuses a name that is in use:**
    - A server listens on the name, on every platform.
    - The socket file of a server that was killed, with the file that a bound and closed `socket.socket(AF_UNIX)` leaves behind.
    - A regular file at the path.
  - **Requirement Closing a pipe server stops it listening and leaves its connections open:**
    - All three scenarios. The socket file after close runs on Python 3.12, which keeps the file, and in 5.4 on 3.13 and later.
    - An accepted connection after close waits until the server has accepted the connection, because on Windows a close before the accept callback breaks it (design decision 6).

  Counter-checks: without the connection test, A server listens on the name must fail on POSIX. Without the unlink, The socket file after close must fail on 3.12. Without the translation, A server listens on the name must fail on the VM.
- [x] 1.4 Add `create_pipe_subprocess()` to `pipes.py`, with the window rule of `create_stdio_subprocess()` on Windows (design decisions 6 and 10). Add `tests/minimal_pipe_server.py`, a standalone server with only the standard library:
  - It connects to the address of its `--pipe=` argument with blocking I/O: `open()` on Windows, `socket.socket(AF_UNIX)` elsewhere.
  - It prints a line to its stdout, and lets a child process print another.
  - It answers the handshake and `Echo`, and exits at the end of its input.

  Verify in `tests/test_pipe_connection.py`, with a hard time limit on each wait:
  - **Requirement A process can be started with a connection over a pipe, on every platform:**
    - A process that connects with the connection function, with a child script that uses `open_pipe_connection()` and a `JsonRpcPeer`.
    - A process with plain blocking reads and writes, with `tests/minimal_pipe_server.py`.
    - Only the first connection; A process that exits before it connects.
    - Cancelled while it waits for the connection, with `asyncio.wait_for()`.
    - Command that cannot be started; Further arguments.
  - **Requirement On Windows a process started without a console opens no window, for Windows only:** the three scenarios for `create_pipe_subprocess()`, with fakes for `asyncio.create_subprocess_exec()` and `has_console()`, as for `create_stdio_subprocess()`.

  Counter-checks: without the close of the listener, Only the first connection must fail. Without the watch on the process, A process that exits before it connects must fail by its time limit. Without the cleanup on cancellation, Cancelled must find the process still running.

  No Robot test: Robot Framework uses the function through the client, which group 3 covers.
- [x] 1.5 In `packages/jsonrpcpeer/README.md`, add a section Pipes with a snippet in the style of the stdio section. It describes:
  - the four functions and the names on each platform;
  - that `wait_closed()` on Windows does not wait for the connections;
  - the rule for synchronous I/O on Windows from design decision 10.

  Verify by running the snippet on Linux and on the VM.

## 2. The server

- [x] 2.1 In `packages/server/src/robot_jsonrpcremote_server/__main__.py` (design decision 8):
  - Add the mode `pipe-server`.
  - Let `--pipe NAME` and `--pipe-server NAME` take a name, and set mode and name with an `argparse.Action`.
  - Update the help of `--mode`, `--pipe`, `--pipe-server` and `--pipe-name`.
  - Remove the refusal of the mode `pipe` from `run()`.

  Verify in `tests/test_server_cli.py`:
  - Replace `test_run_rejects_unsupported_mode` with tests for the options:
    - `--pipe NAME`, `--pipe=NAME` and `--mode pipe --pipe-name NAME` give the same mode and name, which covers The name as the next argument.
    - `--pipe-server NAME` and `--mode pipe-server` do the same.
    - The help names no planned mode.
  - **Requirement A value from the environment that its option does not take is a usage error:**
    - Keep the tests of its four unchanged scenarios.
    - Drop from `test_unknown_mode_from_the_environment_is_a_usage_error` the check that the error does not say that a mode is not supported yet.
    - Add A pipe mode from the environment, with `ROBOT_JSONRPC_MODE=pipe-server` and `ROBOT_JSONRPC_PIPE_NAME`, where a client connects.

  Counter-check: without `pipe-server` in `_MODES`, A pipe mode from the environment must fail.
- [x] 2.2 Add `run_pipe_client()` for the mode `pipe`, after `run_stdio_server()`, with a start message that names the address (design decision 8). Verify the requirement In pipe mode the server serves the client whose pipe it connects to:
  - In a new `tests/test_server_pipe.py`:
    - A client that listens on a pipe: `create_pipe_subprocess()` starts our server, and the test imports a library and calls a keyword.
    - The end of the connection, with exit code 0.
  - In `tests/test_server_cli.py`, next to `test_server_on_a_port_in_use_fails_to_start`: Nobody listens on the pipe, with exit code 1, the name in the error and no message that the server is up.

  Counter-check: without `remote_context.stop()` at the end of the connection, The end of the connection must fail by its time limit.

  The Robot test for this mode is the suites of 3.4, which start our server over `pipe:`.
- [x] 2.3 Add `run_pipe_server()` for the mode `pipe-server`, after `run_tcp_server()`, with a start message that names the address (design decision 8). Verify the requirement In pipe-server mode the server listens on a pipe for any number of clients:
  - In `tests/test_server_pipe.py`:
    - Two clients at once.
    - The log names the pipe, on Linux and on the VM.
    - Stopping, with SIGINT and with SIGTERM, on POSIX only, because `terminate()` is a hard kill on Windows.
  - In `tests/test_server_cli.py`: The name is in use, with a second server on the same name.

  Counter-check: without the stop hook, Stopping must fail by its time limit.

  The Robot test for this mode is `atests/pipe_server.robot` of 3.6.
- [x] 2.4 Update the server documentation, and review the implementation of 2.1 to 2.3 against the page:
  - In `docs/src/content/docs/reference/server.mdx`:
    - Update the rows of `--mode`, `--pipe` and `--pipe-name`, and add `--pipe-server`.
    - Add a section on the two pipe modes: the names on each platform, who can connect (design decision 9), the failed start for a name in use or a pipe that nobody listens on, the socket file that the server removes, and that the server in pipe mode stops when its connection ends.
  - In `packages/server/README.md`, show `pipe:` as the way for the client to start the server, and link the page Transports.

## 3. The client

- [x] 3.1 In `src/JsonRpcRemote/__init__.py`, let `create_connection()` hand the scheme `pipe` to a new `_Session._create_pipe_connection()`. Implement `pipe:<command>` (design decision 7):
  - `_split_command()` splits the command;
  - `create_pipe_subprocess()` starts it with `stdin=DEVNULL` and `stdout=2`;
  - `_res.process` holds the process;
  - a command that is not found gets the sentence about `pipe://<name>`.

  Verify in `tests/test_client_connection.py` with `tests/minimal_pipe_server.py`:
  - **Requirement A pipe URI with a command starts the server and talks to it over a pipe:**
    - Command with backslashes on Windows, with `sys.platform` patched and the argv recorded, as in `test_a_stdio_command_is_split_as_its_platform_writes_paths`.
    - A server for each session, with a test that a session starts and reaps the server.
    - Command that cannot be found; URI without a command.
  - **Requirement A server started over a pipe gets an empty stdin and writes to the stderr of the client:** Output of the server, with `capfd`: the lines of the minimal server and of its child are on file descriptor 2 and not on 1.

  Counter-checks: without `stdout=2`, Output of the server must fail. Without the sentence, Command that cannot be found must fail. Without `_res.process`, A server for each session must fail.
- [x] 3.2 Implement `pipe://<name>` with `open_pipe_connection()` inside `wait_for()` with `rpc_timeout`. Let `tests/fake_server.py` listen on a pipe with `start_pipe_server()` when it gets a name, with `pipe://<name>` as its `uri` (design decisions 7 and 11).
  - Verify:
    - In `tests/test_client_connection.py`, for the requirement A pipe URI with a name connects to a server that listens on a pipe: Server that listens on a pipe and Nobody listens, against the fake server; Absolute path on POSIX; URI without a name.
    - In `tests/test_client_connect_retry.py`, A server that starts later: `test_import_waits_for_a_server_that_comes_up_within_the_window` also runs against a fake server on a pipe.
  - Counter-check: without the branch for `pipe://`, Server that listens on a pipe must fail.
- [x] 3.3 Let `_create_stdio_connection()` refuse `stdio://` with the form without `//`, and let the error for an unknown scheme name `tcp`, `pipe` and `stdio` (design decision 7).
  - Verify in `tests/test_client_connection.py`, for the requirement A stdio URI has its command right after the colon:
    - stdio with two slashes, with `create_stdio_subprocess()` patched to fail the test if it is called.
    - Unknown scheme, in `test_create_connection_rejects_unknown_scheme`.
  - Counter-check: against the code that drops `//`, stdio with two slashes must fail.
  - No Robot test: the message is the same in a suite, and 3.4 covers how a failed import reaches Robot Framework.
- [x] 3.4 Add the Robot suites for `pipe:`:
  - `atests/pipe_vars.py` holds the commands of `atests/stdio_vars.py` without `--stdio`, built with `shlex.join()`, and a `CHILD_PID_FILE` of its own.
  - The suites `atests/pipe_echo.robot`, `pipe_probe.robot`, `pipe_scope.robot`, `pipe_lost_connection.robot`, `pipe_connect_retry.robot` and `pipe_output.robot` follow their stdio counterparts, with the same libraries.
  - `pipe_echo.robot` also gets a test that `Import Library` with a command that does not exist fails with the sentence about `pipe://`.

  Verify locally and on the VM. This covers:
  - the scenarios Python server, Server that exits during a call, Server that exits while a child process runs, A server for each session and Command that cannot be found of the first client requirement;
  - A child process reads stdin of the second.

  Counter-checks: against the client without `_res.process`, `pipe_lost_connection.robot` must fail, because the message lacks the exit code. Against the code without `stdin=DEVNULL`, run `pipe_output.robot` once with an open pipe that nobody writes as the stdin of `robot`: Child Process Reading Stdin Gets The End Of Its Input must fail there.
- [x] 3.5 Let `atests/node_keywords.js` connect to the address of a `--pipe=` argument with `net.connect()` and use that socket instead of stdin and stdout. Add `atests/pipe_node_server.robot` after `stdio_node_server.robot`, with the wrapper script on Windows. Verify locally and on the VM. This covers Server in another language. Counter-check: against `node_keywords.js` without `--pipe=`, the suite must fail.
- [x] 3.6 Extend `atests/ServerControl.py` (design decision 11):
  - `start_jsonrpc_server()` takes a `pipe` name, starts the server with `--pipe-server` and waits until a connection to the pipe succeeds.
  - `stop_jsonrpc_server()` waits until the pipe is gone.

  Add `atests/pipe_server.robot`:
  - Its suite setup starts a server of its own with `IsolatedServerControl`, and imports two libraries with the same `pipe://` URI.
  - A test imports a library from a pipe that nobody listens on and checks that the import fails with its name.

  Verify locally and on the VM. This covers Server that listens on a pipe, Two libraries on one server and Nobody listens of the requirement for `pipe://`, and Two clients at once of the server. Counter-check: against the client without the branch for `pipe://`, the suite must fail.
- [x] 3.7 Document the transports:
  - **The guide:** rename `docs/src/content/docs/guides/tcp-and-stdio.mdx` to `guides/transports.mdx`, with the title Transports, and rewrite it after design decision 12:
    - the table of `pipe:`, `pipe://`, `tcp://` and `stdio:`;
    - `pipe:` first, with where the server's output goes and its empty stdin;
    - `pipe://` with `--pipe-server` and the names;
    - who can connect;
    - TCP with its caution;
    - stdio for servers that speak only stdio.
  - **Links:** update the sidebar in `docs/astro.config.mjs` and the links in `reference/library.mdx`, `reference/server.mdx`, `reference/protocol.mdx`, `roadmap.mdx`, `guides/container.mdx` and `packages/server/README.md`. In `reference/library.mdx`, list the four forms of `uri`.
  - **Examples:**
    - Add `docs/examples/pipe/`, the suite of Getting started with `uri=pipe:robot-jsonrpcremote-server --pythonpath . MyLibrary`.
    - Add `docs/examples/pipe-server/`, with `robot-jsonrpcremote-server --pipe-server robot.sock --pythonpath . MyLibrary` and `uri=pipe://robot.sock`.
    - Show both on the page.
    - Add `test_pipe` and `test_pipe_server` to `tests/test_docs_examples.py`, the second with a helper that waits for the pipe instead of port 8271.
    - Add `docs/examples/pipe-server/robot.sock` to `.gitignore`.
  - **Roadmap and overview pages:**
    - In `docs/src/content/docs/roadmap.mdx`, list named pipes and Unix domain sockets as available, with the functions of `jsonrpcpeer`, and keep WebSockets, Streamable HTTP and TLS as planned.
    - On the home page `index.mdx`, the page `why-jsonrpcremote.mdx` and in `README.md`, say that the client starts the server over a pipe or stdio. Where `README.md` lists the guides, it names the transports instead of TCP and stdio.

  Review the implementation of 3.1 to 3.6 against the pages. Verify with `uv run --all-packages pytest tests/test_docs_examples.py` on Linux and on the VM, and with `npm ci` and `npm run build` in `docs/`, which also checks the links.

## 4. The example server

- [x] 4.1 Let `examples/simple-robot-jsonrpcserver/src/simple_robot_jsonrpcserver/__main__.py` take `--pipe ADDRESS`, also as `--pipe=ADDRESS`, and serve one client over `open_pipe_connection()`. Describe it in its README.
  - Add `atests/pipe_own_server.robot` after `stdio_own_server.robot`.
  - Add `test_the_example_server_serves_a_whole_session_over_a_pipe` to `tests/test_example_server.py`, with `create_pipe_subprocess()`.

  Verify locally and on the VM. Counter-check: against the example server without `--pipe`, both must fail.
- [x] 4.2 In `docs/src/content/docs/reference/protocol.mdx`, add a section on servers over a pipe:
  - the convention of `--pipe=<address>`;
  - the addresses on each platform;
  - the rule for synchronous I/O on Windows (design decision 10);
  - the example server with `docs/examples/own-server/echo_pipe.robot`, which `test_own_server` in `tests/test_docs_examples.py` also runs.

  Review 4.1 and 3.5 against the page, and verify with `npm run build` in `docs/`.

## 5. Integration checks

- [x] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform win32` and `uv run --all-packages pytest`; verify all pass.
- [x] 5.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"`; verify all Robot suites pass, the pipe suites included.
- [x] 5.3 On the Windows test VM, run the unit tests and `robotcode run`:
  - with `uv sync --all-packages` and hard time limits;
  - on Python 3.12, 3.14, 3.15 and 3.14t, and with Robot Framework 7.2.

  Verify that all pass, that the pipe suites ran and were not skipped, and that no process stays behind.
- [x] 5.4 Run the unit tests and all Robot suites on Linux with Python 3.13, 3.14, 3.15 and 3.14t by the recipe for several Python versions. Verify all pass, 3.13 included, which removes the socket file itself.
- [x] 5.5 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`). Stage only the paths of this change, because another session may work on `main`.
  - **Subject:** `feat: add a pipe transport`.
  - **Body:** why a server that the client starts gets a pipe of its own, the two directions with the convention of LSP, the proactor's functions on Windows, the names, and that `--pipe` takes a name now. No `BREAKING CHANGE` footer, because the flag never started a server.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`. Check that CI and the docs workflow pass. The uploaded `output.xml` must show that the pipe suites ran on `ubuntu-latest`, `macos-latest` and `windows-latest` and were not skipped. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive` and sync its delta specs into `openspec/specs/jsonrpc-peer`, `openspec/specs/client` and `openspec/specs/server`.
- In the backlog, mark NET-1 and NET-3 as done, and add the third part of NET-5.
