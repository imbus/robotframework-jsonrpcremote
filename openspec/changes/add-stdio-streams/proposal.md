# Proposal

## Why

`JsonRpcPeer` works with any `asyncio.StreamReader` and `asyncio.StreamWriter`, but a Python process that its client starts has nothing to call to get such a pair for its stdin and stdout. The code exists only privately in the server, in `_stdio_streams()`, and every example uses TCP. A library that speaks the protocol directly, without the server package, has to write this code itself.

Whoever copies that code also copies its problem. In stdio mode, file descriptor 1 is the protocol channel, and everything that writes to it corrupts the stream:

- **The server:** a child process that inherits stdout, `Log To Console`, `logger.console()`, or a thread that prints after a keyword returned. The client cannot decode the next frame, and the call hangs. Robot Framework captures only `print()` during an import or a keyword.
- **A hand-written server:** the example server `examples/simple-robot-jsonrpcserver` prints on every message. Over stdio with the streams left in place, the connection broke from the 1 MiB test on, on Linux and on Windows.

File descriptor 0 has a similar problem. A child process that reads stdin takes bytes of the protocol. And a child process that outlives the server keeps both pipes open, so the client sees the end of the connection only when that child ends. That took 25 seconds instead of 2 in a test on Linux.

So the function for the pair must also move the standard streams out of the way, with no option to leave them. This is the core of backlog item NET-6, so this change replaces the planned change `fix-server-stdio-stdout`, and it is the first piece of NET-5.

This is the first of two changes. `add-windows-stdio` adds the Windows path to the same function; asyncio has no working pair for it there, and the server refuses stdio on Windows today. Named pipes and Unix domain sockets are separate items (NET-1, NET-3).

Free-threaded Python came up in the same work. By hand, on 2026-11-02, it passed on 3.14t on Linux and on Windows with the GIL off. CI does not run such a build, because change `add-ci-version-matrix` left it out at the time, so nothing keeps it working. Daniel decided to add a job with this change.

## What Changes

- **New function in `jsonrpcpeer`:** `await open_stdio_connection()` returns a reader and a writer for the stdin and stdout of the current process, named after `asyncio.open_connection()`. It works on POSIX; on Windows it raises the error that the server raises there today, until `add-windows-stdio`.
- **The standard streams move, always:** the connection uses private duplicates that child processes do not inherit. Stdin then reads from the null device, and stdout writes to stderr. This covers `print()`, direct writes to file descriptor 1, Robot Framework's console output, C code and child processes.
- **The pair closes like the pair of a socket:** `writer.wait_closed()` works, which it does not do for the server's pair today, and closing the writer also ends the reader.
- **Server:** stdio mode uses the new function. `_stdio_streams()` is removed, and `_check_stdio_stdin()` moves into the new module.
- **Example server:** `simple-robot-jsonrpcserver --stdio` serves one client over stdio with the new function.
- **CI:** the test job also runs on the free-threaded build 3.14t on all three operating systems, and fails if the GIL is on.
- **Docs:** the page TCP and stdio says where output goes instead of forbidding it, and its example runs a child process that writes to stdout. The protocol page and the README of `jsonrpcpeer` show the new function. Getting started names the free-threaded build, and the roadmap lists what is new.
- **Change `fix-server-stdio-stdout` is removed with the plan of this change:** its proposal is covered here. It had no other artifacts.
- **Not in this change:** Windows, a general transport interface, a thread fallback, a classifier for free-threading.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: new requirements for the connection over stdin and stdout: the pair, the moved streams, what it refuses and how it closes.
- `server`: new requirements that in stdio mode only protocol messages reach the client, that keywords see an empty stdin, and that a child process does not hide the end of the server.

## Impact

- **Peer:** new `packages/jsonrpcpeer/src/jsonrpcpeer/stdio.py`, an export in `__init__.py`, `packages/jsonrpcpeer/README.md`. `peer.py` only loses an outdated comment.
- **Server:** `packages/server/src/robot_jsonrpcremote_server/__main__.py`.
- **Example:** `examples/simple-robot-jsonrpcserver` (`__main__.py`, README).
- **Tests:** new `tests/test_stdio_connection.py`, `atests/stdio_output.robot`, `atests/StdioOutputLib.py`, `atests/stdio_own_server.robot`; `tests/test_server_stdio.py` and `tests/test_example_server.py` change.
- **CI:** `.github/workflows/ci.yml`.
- **Docs:** `docs/src/content/docs/guides/tcp-and-stdio.mdx`, `reference/protocol.mdx`, `getting-started.mdx`, `roadmap.mdx`, `docs/examples/stdio`, `docs/examples/own-server`.
- **Behavior:** output that used to corrupt the stream now appears on the server's stderr, and so on the console of `robot`.
- **Order:** independent of the other open changes, so it can come at any time. `add-windows-stdio` builds on this change.
