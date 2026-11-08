# Proposal

## Why

The client can start a server only over stdio today. Then the server's stdout belongs to the connection, so everything else that writes there has to be moved out of the way. On Windows this took overlapped pipes, a thread per synchronous pipe and care with handles that a launcher hands down. A pipe of its own leaves stdin and stdout alone. That is how the Language Server Protocol does it: `vscode-languageclient` listens on a new pipe and starts the server with `--pipe=<name>`, and RobotCode's language server uses pipes by default.

A server that you start yourself can listen on a pipe instead of a TCP port. Locally, that is safer than TCP. On the loopback address, every local user can connect and run keywords. A named pipe, as asyncio creates it, lets only the user who started the server, administrators and SYSTEM write to it. A Unix domain socket admits whoever may write its file.

On Windows, asyncio's proactor event loop has the functions for named pipes, `create_pipe_connection()` and `start_serving_pipe()`. They are not documented, but RobotCode uses them, and a probe on the Windows test VM confirmed what the design relies on.

## What Changes

- **`pipe:<command>`, a new URI for servers that the client starts:**
  - The client listens on a new address, starts the command with `--pipe=<address>` as its last argument, takes the first connection and stops listening.
  - It is the form that the documentation recommends for servers that the client starts. `stdio:<command>` stays for servers that speak only stdio.
  - The server gets the null device as stdin, and what it writes to stdout goes to the stderr of `robot`, where its stderr goes too.
- **`pipe://<name>`, a new URI for a server that listens on a pipe:** connect retry works as for TCP.
- **Names:**
  - On Windows, a bare name becomes `\\.\pipe\<name>`, and a name that starts with `\\` or `//` is used as written.
  - Elsewhere, the name is the path of a Unix domain socket as written, relative to the working directory.
- **Server:**
  - `--pipe <name>`, also `--pipe=<name>` or `--mode pipe` with `--pipe-name`, connects to the pipe, serves that one client and ends with its connection, as stdio mode does. **BREAKING** for the reserved flag `--pipe`, which now takes a name.
  - `--pipe-server <name>`, or `--mode pipe-server`, listens for any number of clients, as TCP mode does.
  - A name in use is a failed start on every platform. Without that check, asyncio would let a second server on POSIX take the socket file of a running one.
  - When it stops, the server removes its socket file.
- **New functions in `jsonrpcpeer`,** named after their asyncio counterparts: `pipe_address(name)`, `open_pipe_connection(name)`, `start_pipe_server(client_connected_cb, name)` and `create_pipe_subprocess(*argv, **kwargs)`.
- **`stdio://<command>`:** the client no longer reads it as `stdio:<command>`, and says so. The form was never documented, and `//` now means a connection.
- **Example server and Node test server:** both accept `--pipe=<address>`.
- **Docs:**
  - The guide TCP and stdio becomes Transports and puts `pipe:` first for servers that the client starts.
  - The references of the library, the server and the protocol, the roadmap, the overview pages and the READMEs describe the pipes.
  - New runnable examples cover `pipe:`, `pipe://` and the example server over a pipe.
- **Not in this change:**
  - Hardening the named pipes on Windows: restricting them to the own user, rejecting remote clients, and checking the owner of a pipe against a taken name. This becomes a backlog entry.
  - A TCP port that the client listens on, `--socket=` in LSP, and `--clientProcessId`.
  - Changes to RobotCode.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jsonrpc-peer`: new requirements for pipe names, for listening on a pipe and connecting to it, and for starting a process with a connection over a pipe; the requirement about windows of started processes also covers `create_pipe_subprocess()`.
- `client`: new requirements for the `pipe:` and `pipe://` URIs and for `stdio://`.
- `server`: new requirements for pipe mode and pipe-server mode. The requirement for values from the environment refused the reserved mode `pipe`. It is replaced by one that states the same rule without that mode, because OpenSpec cannot drop a scenario from a modified requirement.

## Impact

- **Peer:** new `packages/jsonrpcpeer/src/jsonrpcpeer/pipes.py`, its Windows part in `_win32_pipes.py`, exports in `__init__.py`, `packages/jsonrpcpeer/README.md`.
- **Client:** `_Session.create_connection` and a new `_Session._create_pipe_connection` in `src/JsonRpcRemote/__init__.py`.
- **Server:** the modes, options and two transport functions in `packages/server/src/robot_jsonrpcremote_server/__main__.py`, and `packages/server/README.md`.
- **Example:** `examples/simple-robot-jsonrpcserver/src/simple_robot_jsonrpcserver/__main__.py` and its README.
- **Tests:**
  - New: `tests/test_pipe_connection.py`, `tests/minimal_pipe_server.py`, `tests/test_server_pipe.py`, `atests/pipe_vars.py` and `atests/pipe_*.robot`.
  - Changed: `tests/test_client_connection.py`, `tests/test_client_connect_retry.py`, `tests/fake_server.py`, `tests/test_server_cli.py`, `tests/test_example_server.py`, `tests/test_docs_examples.py`, `atests/node_keywords.js` and `atests/ServerControl.py`.
- **Docs:**
  - `docs/src/content/docs/guides/tcp-and-stdio.mdx` becomes `guides/transports.mdx`.
  - Changed: `reference/library.mdx`, `reference/server.mdx`, `reference/protocol.mdx`, `roadmap.mdx`, `index.mdx`, `why-jsonrpcremote.mdx`, `docs/astro.config.mjs` and `README.md`.
  - New: `docs/examples/pipe/`, `docs/examples/pipe-server/` and `docs/examples/own-server/echo_pipe.robot`.
- **`tcp://` and `stdio:`:** unchanged, except that `stdio://` is refused.
- **Order:** after `add-windows-stdio`, whose event loop setup and window rule this change reuses. Independent of `clarify-global-library-scope`.
