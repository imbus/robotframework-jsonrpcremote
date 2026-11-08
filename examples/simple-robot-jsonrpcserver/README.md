# simple-robot-jsonrpcserver

A minimal, **hand-written** JSON-RPC 2.0 remote server built directly on `jsonrpcpeer` and `robotframework-jsonrpcremote-protocol` — without the ready-made `robotframework-jsonrpcremote-server` package. It shows how to implement the protocol handlers yourself.

It exposes a single library, `SimpleRobotLibrary`, with one keyword:

*   **`Echo`** — returns the given `message` unchanged, and emits a few `robot/log` notifications while it runs (to demonstrate live log forwarding).

## Run it

```bash
uv run simple-robot-jsonrpcserver
```

The server listens on `tcp://127.0.0.1:8271`. With `--pipe ADDRESS`, it connects to the pipe at that address and serves the client that listens there, and with `--stdio`, it serves one client over its stdin and stdout. In both cases, the client can start it itself.

## Use it from Robot Framework

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=SimpleRobotLibrary

*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
```

Over a pipe, the client starts the server for the session and appends `--pipe=ADDRESS` to the command:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=pipe:simple-robot-jsonrpcserver    library_name=SimpleRobotLibrary
```

Over stdio, too:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=stdio:simple-robot-jsonrpcserver --stdio    library_name=SimpleRobotLibrary
```

## What it demonstrates

*   Implementing the definition `ServerEndpoint` from `robot_jsonrpcremote_protocol`, which states the messages `robot/initialize`, `robot/initialized`, `robot/set_log_level`, `robot/import_library`, `robot/run_keyword`, `robot/finalize_library`, `robot/shutdown` and `robot/exit`, with their names and types.
*   Returning a `LibraryDefinition` (keywords, arguments, docs) on import.
*   Sending `robot/log` notifications to the client *during* keyword execution, through the definition `ClientEndpoint`.
*   Accepting clients over TCP via `asyncio.start_server`, or serving one client: over the pipe of the client via `open_pipe_connection()` from `jsonrpcpeer`, or over stdin and stdout via `open_stdio_connection()`. The latter moves stdout to stderr, so the server's `print()` calls do not get in the way of the messages.

See [`src/simple_robot_jsonrpcserver/__main__.py`](src/simple_robot_jsonrpcserver/__main__.py) for the full implementation. The [protocol page](https://imbus.github.io/robotframework-jsonrpcremote/reference/protocol/) of the documentation describes the messages it handles and runs this server with a suite.
