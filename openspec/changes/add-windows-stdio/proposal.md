# Proposal

## Why

On Windows, a Python process cannot use its stdin and stdout with asyncio. Giving `sys.stdin.buffer` to the proactor event loop fails with WinError 6, because it holds a file descriptor of the C runtime and not a handle. Giving it the real handle fails with WinError 87 on the pipes that `subprocess` and asyncio create, because I/O completion ports need overlapped handles, and whoever creates a pipe decides that. So the server refuses stdio mode there, `open_stdio_connection()` from `add-stdio-streams` raises the same error, and the page TCP and stdio says POSIX only.

The client itself already works on Windows against a server in another language: a Node server passed all its tests with the pipes that the client creates today, because Node's libuv also handles synchronous pipes, with threads. Only Python servers have no way in, both our server and hand-written libraries.

Threads would solve that, but they bend a platform that supports this directly. A 256-byte round trip took 273 µs over overlapped pipes and 644 µs with threads on Python 3.12, with TCP at 422 µs. Through Robot Framework the difference hardly shows, at about 2 ms per keyword call. Daniel decided against threads. So the client creates overlapped pipes for the server it starts, and `open_stdio_connection()` uses them through I/O completion ports.

A prototype of this ran on a Windows 11 VM; the design has the results.

## What Changes

- **`open_stdio_connection()` works on Windows:** it uses the handles of stdin and stdout through the proactor event loop, without threads, and moves the standard streams as on POSIX, including the handles that child processes inherit. It raises a `RuntimeError` that names the reason if a handle is not overlapped or the event loop is not a proactor.
- **New function in `jsonrpcpeer`:** `await create_stdio_subprocess(*argv, **kwargs)` starts a process and returns it with a reader and a writer for its stdin and stdout, with overlapped pipes on Windows and ordinary pipes elsewhere.
- **Client:** the `stdio:` transport uses the new function. On Windows, a backslash in the command is an ordinary character, the session runs on a proactor event loop whatever policy the process has set, and a server started by a client without a console opens no window.
- **Server:** `--stdio` works on Windows, with a clear failed start if its pipes are not overlapped.
- **Tests:** the stdio tests and suites run on Windows too, and `atests/stdio_windows.robot` is removed. A new suite runs a server written in Node on all three operating systems.
- **CI:** the lint job also type-checks the code for Windows, with `mypy --platform win32`.
- **Docs:** the pages drop POSIX only, and the protocol page gives the rule for a server of your own on Windows: stdin and stdout are overlapped pipes there, which is fine for one reader and one writer, and not for a child process that inherits them.
- **Not in this change:**
  - The hang of keyword calls that Robot Framework's restarts of the proactor event loop can cause on any transport, about 1 per 100,000 calls on an Insider build of Windows 11.
  - A thread fallback for synchronous handles.
  - Named pipes and Unix domain sockets (NET-1, NET-3).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: new requirements for the connection over stdin and stdout on Windows, and for starting a process with such a connection.
- `client`: new requirements for the `stdio:` transport on Windows.
- `server`: new requirements for stdio mode on Windows.

## Impact

- **Peer:** `packages/jsonrpcpeer/src/jsonrpcpeer/stdio.py`, new `_win32_pipes.py`, an export in `__init__.py`, `packages/jsonrpcpeer/README.md`.
- **Client:** `_Session._create_stdio_connection`, `_Session._run` in `src/JsonRpcRemote/__init__.py`.
- **Server:** the help of `--stdio` in `__main__.py`, `packages/server/README.md`.
- **Tests:** `tests/test_stdio_connection.py`, `tests/test_client_connection.py`, `tests/test_server_cli.py`, `tests/test_server_stdio.py`, `atests/stdio_*.robot`, `robot.toml`; new `atests/stdio_node_server.robot` and `atests/node_keywords.js`.
- **CI:** `.github/workflows/ci.yml`.
- **Docs:** `docs/src/content/docs/guides/tcp-and-stdio.mdx`, `reference/server.mdx`, `reference/protocol.mdx`, `roadmap.mdx`.
- **Behavior on POSIX:** unchanged.
- **Foreign servers on Windows:** every server that the client starts gets overlapped pipes, because the client cannot tell what it starts. See the design for what was measured.
- **Order:** after `add-stdio-streams`, whose function and tests this change extends.
