# robotframework-jsonrpcremote-server

A **Robot Framework Remote Server** powered by **JSON-RPC 2.0**. It hosts your existing Robot Framework libraries and exposes them to remote clients such as `JsonRpcRemote` over a modern, bidirectional protocol.

## Features

* **Robot-first:** Runs regular Robot Framework libraries without code changes.
* **JSON-RPC 2.0:** Uses the same protocol contract as the client package for requests, responses, and log notifications.
* **Live logging:** Forwards Robot log messages to the connected client while keywords execute.
* **Efficient core:** Designed for multiple concurrent clients.
* **Scoped imports:** Restrict which libraries may be imported by passing them explicitly on startup.
* **Configurable transport:** TCP and stdio are implemented today; the pipe mode is wired but not implemented yet.

## Installation

```bash
pip install robotframework-jsonrpcremote-server
```

Requires **Python >= 3.10** and **Robot Framework >= 7.2**.

## Quick start (TCP)

Expose one or more Robot Framework libraries over TCP (default port `8271`, default bind `127.0.0.1`).

```bash
robot-jsonrpcremote-server --bind 0.0.0.0 --port 8271 MyLibrary
```

Then point your client library to `tcp://<host>:8271`:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=MyLibrary
```

If the server cannot start, for example because the port is already in use, it logs `Server failed to start: <reason>` and exits with exit code 1.

## Quick start (stdio)

In stdio mode the server serves a **single client** over its stdin/stdout, so the client
launches it as a subprocess (LSP-style) -- no network port required. The client supplies the
full command via a `stdio:<command>` URI:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=stdio:robot-jsonrpcremote-server --stdio MyLibrary    library_name=MyLibrary
```

**Notes for stdio mode:**

- **POSIX only.** The Windows asyncio event loop cannot attach to stdin; the server raises a
  clear error there. Use TCP on Windows.
- **Keep stdout clean.** stdout carries the JSON-RPC frames. The server's own logs go to
  stderr, but a hosted keyword library that `print()`s to stdout will corrupt the stream --
  route such output to stderr (or use Robot's logging) instead.
- **stdin must be a pipe.** stdio mode needs a pipe or socket on stdin, as a client that
  launches the server provides. With `/dev/null` or a regular file on stdin, the server fails
  to start with exit code 1 instead of waiting for input -- so start a Docker container that
  runs the server in stdio mode with `-i`.

## CLI options

```text
robot-jsonrpcremote-server [options] LIBRARY [LIBRARY ...]
```

- `--bind ADDRESS` (repeatable): Address(es) to bind. Defaults to `127.0.0.1`. Also accepts comma-separated `ROBOT_JSONRPC_BIND`.
- `--port PORT`: TCP port (default `8271` or `ROBOT_JSONRPC_PORT`).
- `--mode {tcp,stdio,pipe}`: Server mode (`tcp` and `stdio` today; `pipe` not implemented yet). `--tcp`/`--stdio` are aliases.
- `--stdio`: Serve a single client over stdin/stdout (POSIX only). Alias for `--mode stdio`.
- `--pipe-name NAME`: Pipe name for future pipe mode (default `robot_jsonrpcremote_pipe` or `ROBOT_JSONRPC_PIPE_NAME`).
- `--pythonpath/-P PATH` (repeatable): Additional directories made importable before loading libraries, like robot's `--pythonpath`. Lets you serve libraries that live outside the installed packages.
- `--variable name:value` (repeatable): Set an individual Robot variable, like robot's `--variable`. (No `-v` alias here, since `-v` is `--verbose`.)
- `--variablefile/-V PATH` (repeatable): Load variables from a file, like robot's `--variablefile`.
- `--outputdir/-d DIR`: Directory for Robot output files, like robot's `--outputdir`.
- `-v/--verbose`: Enable debug logging.
- `--version`: Show version.
- Positional `LIBRARY`: One or more libraries allowed to load. If provided, only these are accepted by clients.

## Environment variables

- `ROBOT_JSONRPC_MODE`: Default server mode (fallback to `tcp`).
- `ROBOT_JSONRPC_BIND`: Comma-separated bind addresses.
- `ROBOT_JSONRPC_PORT`: Default port.
- `ROBOT_JSONRPC_PIPE_NAME`: Default pipe name placeholder.

## Stopping the server

Stop the server with SIGTERM or SIGINT (Ctrl+C), for example when a container is stopped. It then:

1. stops accepting connections;
2. lets the keyword that is running finish and delivers its result to the client;
3. answers requests that need the Robot runner (importing or finalizing a library, running a keyword) and are still waiting or arrive now with the error `server is shutting down`, without running them;
4. closes every client connection and exits with code 0.

The server waits up to 5 seconds for the responses still being sent before it closes the connections. A keyword that does not return delays the stop, since Robot Framework runs it synchronously and the server cannot interrupt it; such a server has to be killed, as Kubernetes does after the pod's termination grace period.

The client reports the closed connection as a lost connection for the rest of its session. In stdio mode, the server also stops when the client closes the server's stdin.

## License

Apache-2.0
