# simple-robot-jsonrpcserver

A minimal, **hand-written** JSON-RPC 2.0 remote server built directly on `jsonrpcpeer` and `robotframework-jsonrpcremote-protocol` — without the ready-made `robotframework-jsonrpcremote-server` package. It shows how to implement the protocol handlers yourself.

It exposes a single library, `SimpleRobotLibrary`, with one keyword:

*   **`Echo`** — returns the given `message` unchanged, and emits a few `robot/log` notifications while it runs (to demonstrate live log forwarding).

## Run it

```bash
uv run simple-robot-jsonrpcserver
```

The server listens on `tcp://127.0.0.1:8271`.

## Use it from Robot Framework

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=SimpleRobotLibrary

*** Test Cases ***
Echo Returns The Message
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
```

## What it demonstrates

*   Implementing the protocol handlers — `robot/initialize`, `robot/initialized`, `robot/import_library`, `robot/run_keyword` — with the `@rpc_request` / `@rpc_notification` decorators from `jsonrpcpeer`.
*   Returning a `LibraryDefinition` (keywords, arguments, docs) on import.
*   Sending `robot/log` notifications to the client *during* keyword execution.
*   Accepting clients over TCP via `asyncio.start_server`.

See [`src/simple_robot_jsonrpcserver/__main__.py`](src/simple_robot_jsonrpcserver/__main__.py) for the full implementation.
</content>
