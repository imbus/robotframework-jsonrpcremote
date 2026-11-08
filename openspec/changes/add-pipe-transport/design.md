# Design

## Context

See proposal.md for the motivation. The starting point:

- **Client:** it knows `tcp://` and `stdio:<command>`, and rejects any other scheme. Its session runs on a proactor event loop on Windows, whatever policy the process has set (`add-windows-stdio`, decision 7). It retries every failed connection attempt: `_connect_with_retry()` catches any `Exception`.
- **Server:** it runs its asyncio loop in a thread of its own. `run_tcp_server()` serves many clients and `run_stdio_server()` serves one. The mode `pipe`, the flag `--pipe` and `--pipe-name` with `ROBOT_JSONRPC_PIPE_NAME` are reserved, and `run()` refuses the mode.
- **`jsonrpcpeer`:** it has `open_stdio_connection()` and `create_stdio_subprocess()`. Their Windows code lives in `_win32_pipes.py`, including `has_console()` for the window rule.
- **Prior art:**
  - **`vscode-languageclient` 11:** for a command with `TransportKind.pipe`, it makes a random name: `\\.\pipe\lsp-<32 hex digits>-sock` on Windows, otherwise a socket file in `$XDG_RUNTIME_DIR` or the temp directory, shortened to 107 characters on Linux and 102 on macOS. It listens there, starts the server with `--pipe=<name>` as the last argument, takes the first connection and closes its listener. It passes `--clientProcessId` only to Node modules. The source is in RobotCode's `node_modules`.
  - **RobotCode:** `start_pipe()` and `start_pipe_server()` in `packages/jsonrpc2/src/robotcode/jsonrpc2/server.py` use the proactor's `create_pipe_connection()` and `start_serving_pipe()` on Windows, and `create_unix_connection()` and `create_unix_server()` elsewhere. Its language server runs over `pipe` by default. Its debug launcher runs with `--pipe-server <random path>`, and VS Code checks every 100 ms whether the file exists.
- **CPython source:**
  - **`start_serving_pipe()`:** it makes every instance with `CreateNamedPipe()`, in message mode, with no security attributes, and without `PIPE_REJECT_REMOTE_CLIENTS`. The first instance has `FILE_FLAG_FIRST_PIPE_INSTANCE`. It returns a list with one `PipeServer`.
  - **`connect_pipe()`:** it repeats `CreateFile()` only for `ERROR_PIPE_BUSY`. Both functions exist in `asyncio/windows_events.py` of 3.12 to 3.15.
  - **`create_unix_server()`:** it removes an existing socket file before it binds (`unix_events.py`, line 309 in 3.12). From 3.13 on, it also removes the file when the server is closed (`cleanup_socket`).

**Probes,** on Linux with Python 3.12 and 3.13, and on the Windows test VM with 3.12.16 and 3.14.10, with the same result on both versions:

| Probe | Windows (named pipe) | Linux (Unix domain socket) |
|---|---|---|
| 1 MiB in both directions with `StreamReader` and `StreamWriter` | passes, also with the server's loop in a thread of its own | passes |
| A second server on the name | `PermissionError`, WinError 5 | starts without an error and takes the path over from the running one |
| No server | `FileNotFoundError`, WinError 2, without the name in the message | `FileNotFoundError`, without the path; `ConnectionRefusedError` for a socket file that is left over |
| A bare name | `create_pipe_connection("probe_win.py")` opens the regular file of that name | a path relative to the working directory |
| `//./pipe/<name>` | works as `\\.\pipe\<name>` | – |
| `close()` of the server | accepted connections keep working; one whose accept callback had not run yet breaks with `BrokenPipeError`, WinError 232; new connections get `FileNotFoundError` | 3.12 leaves the socket file behind, 3.13 removes it |
| `os.path.exists()` on the name | `True`, and the server sees a connection | – |
| The client listens, and a child started with `--pipe=<name>` connects | after 0.27 s, 1 MiB in both directions, and the child exits with 0 once the parent closes its writer | – |
| A pipe opened with `open()`, without overlapped I/O | a write while a read waits takes 1.5 s, until the read returns | – |
| Node's `net.connect(name)` | 1 MiB in both directions | – |
| Rights of the socket file | – | 0755 with umask 022 |
| A path of 120 characters, or a regular file at the path | – | `OSError: AF_UNIX path too long`, or `EADDRINUSE` with the path |

## Goals / Non-Goals

**Goals:**

- A server that the client starts gets a connection of its own, and its stdin and stdout stay out of the protocol.
- A server that you start yourself can listen locally on a pipe instead of a TCP port, with the same behavior for its clients.
- One set of functions in `jsonrpcpeer` for both directions on all three platforms, which our client, our server, the example server and later RobotCode can use.
- The convention of LSP, so that LSP-style servers in other languages fit.

**Non-Goals:**

- Hardening the named pipes on Windows beyond what the proactor creates (decision 9, backlog SEC-3).
- A TCP port that the client listens on (`--socket=` of LSP), and Unix sockets in the abstract namespace of Linux.
- Changing `tcp://` or `stdio:`, other than refusing `stdio://`.

## Decisions

### 1. Two directions, and the client listens for the server it starts

For `pipe:<command>`, the client listens on a new address and starts the command with `--pipe=<address>` as its last argument. It takes the first connection and stops listening. That is what `vscode-languageclient` does, and how RobotCode's language server runs by default. For `pipe://<name>`, the server listens, started with `--pipe-server <name>`, as RobotCode's debug launcher does.

**Alternatives:**

- **The server listens on a random name, and the client waits for it,** as VS Code does for the debug launcher. The client would have to poll. On Windows, `os.path.exists()` on a pipe name connects to the pipe (probe), so a check would take the server's first connection. While the client waits for a connection, it notices at once when the process exits. A poll cannot tell a server that is still starting from one that hangs.
- **A scheme without the transport,** such as `start:<command>`, with pipes as its default. Daniel chose the explicit `pipe:` next to `stdio:`.
- **`--clientProcessId`:** not needed. In pipe mode, the server ends with its connection, and the connection ends when the client process ends.

### 2. Named pipes through the proactor, Unix domain sockets through asyncio

- **Windows:** `ProactorEventLoop.create_pipe_connection()` and `start_serving_pipe()` give a duplex transport over I/O completion ports, the mechanism that `add-windows-stdio` uses for overlapped pipes, over one handle.
- **Elsewhere:** `asyncio.open_unix_connection()` and `asyncio.start_unix_server()`.

**Alternatives:**

- **Our own `CreateNamedPipe()` through ctypes:** Daniel chose the proactor. Code of our own is the way for the later hardening (decision 9).
- **`AF_UNIX` on Windows:** Windows supports it, but Python's `socket` module does not offer it there, and asyncio has no Unix functions on Windows.

### 3. Names

`pipe_address(name)` resolves every name:
- **On Windows:** a name that starts with `\\` or `//` stays as it is, and any other name gets `\\.\pipe\` in front.
- **Elsewhere:** the name stays as it is, as the path of a socket file relative to the working directory unless it is absolute.
- **An empty name** raises `ValueError`.

Why the prefix rule on Windows:
- Robot Framework reads a backslash as an escape, so `\\.\pipe\robot` would have to be written `\\\\.\\pipe\\robot` in a suite.
- With a bare name, the same suite runs on every platform.
- A bare name must never reach `CreateFile()`: `create_pipe_connection("probe_win.py")` opened the regular file of that name (probe).

On POSIX, the path is used as written, as in RobotCode. Daniel chose that over a folder for each user or `$XDG_RUNTIME_DIR`. Processes in different working directories need an absolute path.

The platform sets the limits. A socket path has at most 107 bytes on Linux and 103 on macOS (`sun_path`). Beyond that, Python raises `OSError: AF_UNIX path too long` (probe). On Windows, a pipe name has at most 256 characters.

### 4. The functions in `jsonrpcpeer`

A new module `pipes.py` holds the functions, its Windows part goes to `_win32_pipes.py`, and `__init__.py` exports them:
- **`open_pipe_connection(name)`** returns a `StreamReader` and a `StreamWriter`, as `asyncio.open_unix_connection()` does. On Windows, it builds them from a `StreamReaderProtocol` with `create_pipe_connection()`.
- **`start_pipe_server(client_connected_cb, name)`** returns an `asyncio.AbstractServer`. On POSIX, it is the `asyncio.Server` of `asyncio.start_unix_server()`. On Windows, it is a small subclass of `asyncio.AbstractServer` around the list from `start_serving_pipe()`:
  - `close()` closes the `PipeServer`.
  - `is_serving()` and `get_loop()` work as for `asyncio.Server`.
  - `wait_closed()` returns once the server is closed. It does not wait for the connections, as `asyncio.Server.wait_closed()` does from 3.12.1 on, because the `PipeServer` does not track them. Our server closes its clients itself before, as in TCP mode, and the README says so.
- **Errors name the address.** asyncio's errors do not (probe), so the functions raise the same type with the errno, its text and the address, as `OSError(errno, strerror, filename)` does.
- **An event loop without the pipe functions** on Windows, such as the selector event loop, raises a `RuntimeError` that names the proactor event loop, as `check_loop()` does for stdio. Our client always has a proactor. Our server has the default event loop of Windows, which is a proactor, created before any library is imported.

**Alternatives:**

- **Returning asyncio's list on Windows,** as RobotCode does: every caller would have to tell the platforms apart.
- **A protocol type of our own:** `asyncio.AbstractServer` already fits `set_server()` and the `async with` of our server.

### 5. A name in use

- **On Windows:** a second server fails with `PermissionError` (WinError 5, probe). The reason is `FILE_FLAG_FIRST_PIPE_INSTANCE` on the first instance. `start_pipe_server()` turns that into an `OSError` with `errno.EADDRINUSE` and the address.
- **On POSIX:** asyncio removes an existing socket file before it binds. A second server took over the path of a running one without an error (probe). So `start_pipe_server()` first connects to an existing socket file:
  - If the connection succeeds, it raises the same `EADDRINUSE` error.
  - If the connection is refused, the file is left over, and asyncio replaces it.
  - At a regular file, asyncio raises `EADDRINUSE` itself (probe).
- **Removing the socket file:** 3.12 leaves it behind after `close()`, 3.13 removes it. `start_pipe_server()` removes it on every version, and only if it is still the file that the server bound (the same inode), as 3.13 checks.

**Alternative:** a lock file next to the socket. That is another file to clean up, and the connection answers the real question: whether a server listens.

The check and the bind are not atomic. Two servers that start at the same moment can both pass the check, and then the second wins, as with asyncio alone. That is accepted.

### 6. `create_pipe_subprocess()`

- **The address:**
  - On Windows, it is `\\.\pipe\jsonrpcpeer-<32 hex digits>` from `secrets.token_hex(16)`, as many random bits as `vscode-languageclient` uses.
  - On POSIX, it is `pipe` in a directory from `tempfile.mkdtemp(prefix="jsonrpcpeer-")`, which has the mode 0700. With the `$TMPDIR` of macOS, about 50 characters long, the path has about 80 of the 103 characters that macOS allows.
- **The order:** it listens first and then starts the process with `--pipe=<address>` as its last argument. Then it waits for whichever comes first: the first connection or the end of the process.
- **Closing the listener:** it closes inside the accept callback of the first connection.
  - On Windows, a close before that callback has run breaks the connection that the process has just made (probe), while accepted connections stay open (probe).
  - A further connection that is accepted before the close is closed at once.
  - On POSIX, the socket file and its directory are removed after the first connection, and the connection stays valid.
- **A process that ends before it connects:** the function raises a `ConnectionError` that names the exit code and the address. It reaps the process, because the caller never gets it.
- **Cancellation,** such as the caller's `wait_for()` timeout: the function kills the process, waits for it, closes the listener, removes the address and raises the cancellation again. If the start itself fails, as for a command that does not exist, it also removes the address.
- **The window rule** is that of `create_stdio_subprocess()`: `CREATE_NO_WINDOW` if the caller has no console and passes no `creationflags`. The MODIFIED requirement covers both functions.
- **Further arguments** go to `asyncio.create_subprocess_exec()`. The caller chooses stdin, stdout and stderr (decision 7).

**Alternative:** passing the address in an environment variable. LSP appends it as an argument, and LSP libraries in other languages read `--pipe=`.

### 7. The client

- **Dispatch:** `create_connection()` hands the scheme `pipe` to a new `_create_pipe_connection()`. Text after `pipe:` that starts with `//` is a name, and anything else is a command.
- **`pipe:<command>`:**
  - The command is split with `_split_command()`, as for `stdio:`, with the rule for backslashes on Windows.
  - `create_pipe_subprocess(*argv, stdin=DEVNULL, stdout=2)` runs inside `wait_for()` with `rpc_timeout`, as for stdio.
  - `_res.process` is set, so `close_connection()` reaps the process and the loss message names its exit code, as for stdio.
  - **stdin** is the null device, so that neither the server nor its children read the console of `robot`. A server in stdio mode gives its children an empty stdin for the same reason.
  - **stdout** is the file descriptor 2 of the client process. That is where the output of a stdio server ends up as well, and the console output of `robot` on stdout stays free of the server's output. It is not `sys.stderr`, which Robot Framework replaces while a keyword runs, and a session can start inside a keyword call.
  - **A `FileNotFoundError` at the start** gets a sentence that names `pipe://<name>`. Otherwise `pipe:robot`, with the `//` forgotten, would say only that `robot` was not found.
- **`pipe://<name>`:** `open_pipe_connection(name)` runs inside `wait_for()` with `rpc_timeout`. Connect retry already repeats every error, so `FileNotFoundError` and `ConnectionRefusedError` need nothing new.
- **`stdio://`:** `_create_stdio_connection()` drops `//` today. It now raises a `ValueError` that shows the form without `//`. The error for an unknown scheme names `tcp`, `pipe` and `stdio`.

### 8. The server

- **Modes:** `_MODES` gets `pipe-server`.
- **`--pipe NAME` and `--pipe-server NAME`** take a value and stay in the mutually exclusive group. A small `argparse.Action` sets both `mode` and `pipe_name`, as RobotCode's options do.
  - The flag `--pipe` of today takes a name now. It was reserved and never worked.
  - `--pipe-name` and `ROBOT_JSONRPC_PIPE_NAME` stay, with the default `robot_jsonrpcremote_pipe`.
- **`run()`** no longer refuses the mode `pipe`, and its start message names the address.
- **`run_pipe_client()`,** for the mode `pipe`, works like `run_stdio_server()`: `open_pipe_connection()`, one `handle_client()`, and `remote_context.stop()` at the end. A connection that fails is a failed start, as a TCP port in use is.
- **`run_pipe_server()`,** for the mode `pipe-server`, works like `run_tcp_server()`: `start_pipe_server()`, `set_server()`, the stop hook, and `close()` with `close_clients()` when it stops.
- **In both pipe modes,** stdout stays the server's own, and Robot Framework captures `print()` in a keyword as over TCP.
- **The spec:** the requirement for values from the environment is replaced, through REMOVED and ADDED under a new name. OpenSpec refuses a MODIFIED block that drops the scenario of the reserved mode.

### 9. Who can connect, documented and not changed

- **Windows:** without security attributes, a named pipe gets the default security descriptor. According to Microsoft's documentation of `CreateNamedPipe`, it gives full control to LocalSystem, administrators and the creator owner, and read access to Everyone and the anonymous account. Without `PIPE_REJECT_REMOTE_CLIENTS`, clients on other machines can open the pipe over SMB with these rights. So only the user who started the server, administrators and SYSTEM can send a request. Others can open the pipe for reading only.
- **POSIX:** the socket file gets its rights from the umask (probe: 0755 with umask 022). On Linux, a connection needs write permission on it. A directory that only the user can enter protects on every system.
- **The address of `pipe:`:**
  - On POSIX, it lies in a directory with the mode 0700 (decision 6).
  - On Windows, it has the default descriptor. Another local user who watches for new pipes could connect first, for reading. That user would read the first request of the client, and the session would fail. This is rare.
- **Backlog SEC-3** collects the hardening:
  - our own `CreateNamedPipe()` with a descriptor for the own user only
  - `PIPE_REJECT_REMOTE_CLIENTS`
  - `SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION` when connecting
  - a check of the owner of a pipe server against a name that someone else has taken

### 10. Servers of your own

- **The convention,** on the protocol page: the client appends `--pipe=<address>` as the last argument. The address is a named pipe on Windows and the path of a socket file elsewhere. The server connects to it, serves that one connection and exits when it ends.
- **Node:** `net.connect(address)` handles both kinds (probe on Windows).
- **Windows:** a pipe opened for synchronous I/O, as `open()` does, handles one operation at a time. A write waited until a pending read returned (probe).
  - A server that reads and writes at the same time must open the pipe for overlapped I/O, as asyncio's `create_pipe_connection()` and Node's `net` do.
  - A server that reads a request and then writes its response can use blocking I/O, as `tests/minimal_pipe_server.py` does.
  - RobotCode met the same limit: its run terminals use TCP because the Python script there reads and writes a named pipe at the same time.
- **Our own servers:** the example server gets `--pipe`, with `open_pipe_connection()`, and the Node test server gets `--pipe=`.

### 11. Tests

- **Standalone server:** `tests/test_pipe_connection.py` tests the four functions on every platform with `tests/minimal_pipe_server.py`. That server uses only the standard library and blocking I/O, as `tests/minimal_stdio_server.py` does for stdio.
- **Fake server:** `tests/fake_server.py` learns to listen on a pipe, so that the retry tests of `tests/test_client_connect_retry.py` also run against `pipe://`.
- **Our server:** `tests/test_server_pipe.py` tests both modes. A graceful stop by signal is tested on POSIX only, because `terminate()` is a hard kill on Windows.
- **Robot suites:**
  - They mirror the stdio suites: `pipe_echo`, `pipe_probe`, `pipe_scope`, `pipe_lost_connection`, `pipe_connect_retry`, `pipe_output`, `pipe_node_server` and `pipe_own_server`.
  - Their commands come from `atests/pipe_vars.py`, built with `shlex.join()` as in `stdio_vars.py`, without `--stdio`.
  - `pipe_server.robot` covers `pipe://`, with a server of its own from `IsolatedServerControl`, started with `--pipe-server`. `ServerControl` waits for a pipe by connecting to it, as it does for a port.
- **Short socket paths:** pytest's `tmp_path` can be longer than 103 characters on macOS. So the tests change into it and use relative names, or use a short directory from `tempfile.mkdtemp()`.
- **Windows:** the tests run on the Windows test VM, which Daniel starts on request, and CI runs them on all three platforms.

### 12. Documentation

- **The guide:** TCP and stdio becomes `guides/transports.mdx`, with the title Transports.
  - A table of the four URIs comes first.
  - `pipe:` leads for servers that the client starts. Then follow `pipe://` with `--pipe-server`, the names and who can connect, TCP, and stdio for servers that speak only stdio.
  - The sidebar in `docs/astro.config.mjs` and the links on the other pages and in the READMEs follow the rename.
- **Examples:**
  - `docs/examples/pipe/` has the suite from Getting started with `pipe:`.
  - `docs/examples/pipe-server/` uses `--pipe-server robot.sock` and `pipe://robot.sock`: the same commands on every platform.
  - `docs/examples/own-server/echo_pipe.robot` starts the example server over a pipe.
  - `tests/test_docs_examples.py` runs them, and `.gitignore` covers the socket file of the example.

## Risks / Trade-offs

- [The proactor's pipe functions are not documented] → They exist in 3.12 to 3.15, RobotCode depends on them, and CI tests them on Windows. If they change, the Windows part moves to our own `CreateNamedPipe()` code, which SEC-3 needs anyway.
- [A foreign server must understand `--pipe=`] → `stdio:` stays for servers that speak only stdio, and the protocol page states the convention.
- [Others can open the pipe of `pipe:` for reading on Windows and win the first connection] → Documented and rare; SEC-3.
- [Someone takes a `pipe://` name before the server starts, and the client loads pickles from that process] → It is the same for a TCP port today. SEC-3 covers the check of the owner on Windows, and on POSIX a directory of your own protects you.
- [The check before the bind on POSIX is not atomic] → Accepted (decision 5).
- [The length of socket paths on macOS] → The client's own address is short, the tests use short paths, and the error names the path.
- [`wait_closed()` on Windows does not wait for connections] → The README says so, and our server closes its clients itself.
- [A client that connects while a server stops gets a broken pipe] → The same happens over TCP at that moment.
- [The output of a `pipe:` server reaches the stderr of `robot`] → That is where the output of a stdio server goes, and the guide says so.

## Migration Plan

- **`--pipe`** takes a name now. It was reserved and never started a server.
- **`stdio://<command>`** fails with an error that shows `stdio:<command>`.
- **The URL of the guide** changes from `/guides/tcp-and-stdio/` to `/guides/transports/`, without a redirect, because the site is pre-alpha.
