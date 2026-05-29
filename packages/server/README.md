# robotframework-jsonrpcremote-server

A **Robot Framework Remote Server** powered by **JSON-RPC 2.0**. It hosts your existing Robot Framework libraries and exposes them to remote clients such as `JsonRpcRemote` over a modern, bidirectional protocol.

## Features

* **Robot-first:** Runs regular Robot Framework libraries without code changes.
* **JSON-RPC 2.0:** Uses the same protocol contract as the client package for requests, responses, and log notifications.
* **Live logging:** Forwards Robot log messages to the connected client while keywords execute.
* **Efficient core:** Designed for multiple concurrent clients.
* **Scoped imports:** Restrict which libraries may be imported by passing them explicitly on startup.
* **Configurable transport:** TCP is implemented today; pipe/stdio modes are wired but not implemented yet.

## Installation

```bash
pip install robotframework-jsonrpcremote-server
```

Requires **Python >= 3.10** and **Robot Framework >= 7.0**.

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

## CLI options

```text
robot-jsonrpcremote-server [options] LIBRARY [LIBRARY ...]
```

- `--bind ADDRESS` (repeatable): Address(es) to bind. Defaults to `127.0.0.1`. Also accepts comma-separated `ROBOT_JSONRPC_BIND`.
- `--port PORT`: TCP port (default `8271` or `ROBOT_JSONRPC_PORT`).
- `--mode {tcp,pipe}`: Server mode (`tcp` today; `pipe`/`stdio` not implemented yet).
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


## Development

From the repo root:

```bash
uv sync --all-extras --all-packages --dev
uv build --all-packages
```

## License

Apache-2.0
