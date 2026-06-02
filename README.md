# robotframework-jsonrpcremote

A **Robot Framework Remote Library** implementation using **JSON-RPC 2.0**.

This project enables running Robot Framework keywords on a remote server using the standard **JSON-RPC 2.0** protocol. It serves as an alternative to the standard [Remote Library](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#remote-library-interface).

## Features

*   **JSON-RPC 2.0:** Built on the lightweight and widely supported standard protocol.
*   **Language Agnostic:** Servers can be implemented in any language that supports JSON-RPC 2.0 (e.g., Node.js, Java, C#, Go, Rust, ...).
*   **Transport:** Uses persistent connections. **TCP** and **stdio** are supported today (stdio is POSIX-only and serves a single client). **WebSockets**, **Named Pipes**, **Unix Domain Sockets**, **Streamable HTTP**, and **SSL/TLS** encryption are in development.
*   **Multiplexing:** The architecture supports sharing a single physical connection for multiple library instances (Connection Multiplexing), reducing resource usage.
*   **Asynchronous:** Built on Python's `asyncio`.
*   **Bidirectional Communication:** Allows the server to send **log messages** and progress updates to the client *during* keyword execution.
*   **Dependency Isolation:** Enables running libraries in separate processes or containers.
*   **Multi-Library Support:** A single server instance can host multiple Robot Framework libraries.
*   **Robot Framework Integration:**
    *   Support for **argument conversion** and custom converters.
    *   **Dynamic Initialization** of libraries with arguments.
    *   **Error Handling**: remote keyword failures surface on the client as Robot Framework failures (richer remote-traceback and failure-mode mapping — Fatal/Continuable/Skip — is planned).

## Architecture

The project is organized as a monorepo managed by [uv](https://github.com/astral-sh/uv):

*   **`packages/protocol`**: Defines the JSON-RPC 2.0 protocol messages, data structures, and types.
*   **`packages/jsonrpcpeer`**: An asynchronous JSON-RPC 2.0 peer implementation using `asyncio`.
*   **`packages/server`**: Server runtime components to host library code.
*   **`src/JsonRpcRemote`**: The Robot Framework Client Library (Proxy).
*   **`examples/`**: Runnable usage examples (e.g. a minimal server).
*   **`tests/`**: Unit tests (`tests/unit`, pytest) and Robot Framework integration tests (`tests/robot`).

## Requirements

*   Python >= 3.10
*   Robot Framework >= 7.0

## Installation

You can install the client library using pip:

```bash
pip install robotframework-jsonrpcremote
```

## Usage

### Client (Robot Framework)

Import the `JsonRpcRemote` library in your Robot Framework test suite and specify the URI of the running JSON-RPC server.

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=MyLibrary

*** Test Cases ***
Example Test
    ${result}=    My Keyword    Hello World
    Should Be Equal    ${result}    Hello World
```

**Arguments:**
*   `uri`: The address of the remote server (default: `tcp://127.0.0.1:8271`).
*   `library_name`: The name of the library to initialize on the remote server (optional).
*   `rpc_timeout`: Connection timeout in seconds (default: `10.0`).
*   `rpc_scope`: The scope of the remote session (`TEST`, `SUITE`, `GLOBAL`). Default is `SUITE`.
*   `*args`: Positional arguments passed to the remote library initialization.
*   `**kwargs`: Keyword arguments for the remote library initialization (sent as Robot `name=value` arguments and converted server-side via the library's `__init__` signature).

### Initializing the remote library with arguments

Any **positional** arguments after `library_name` are passed to the remote library's constructor, and any **named** arguments (`name=value`) are forwarded as keyword arguments:

```robot
*** Settings ***
# Positional init arguments
Library    JsonRpcRemote    tcp://127.0.0.1:8271    MyLibrary    ${42}    text

# Named init arguments
Library    JsonRpcRemote    tcp://127.0.0.1:8271    MyLibrary
...            greeting=hello    times=3    enabled=true
```

Argument types are preserved end-to-end: positional values keep their (JSON-serializable) Robot types, and named values are converted **server-side** according to the remote library's `__init__` type hints (so `int`, `float`, `bool`, `Decimal`, `date`, `Enum`, `list`, `dict`, ... all work; without type hints they arrive as strings).

The client's own options — `rpc_timeout` and `rpc_scope` — are consumed by `JsonRpcRemote` itself and are **not** forwarded to the remote library, so you can mix them freely with the library's named init arguments:

```robot
*** Settings ***
Library    JsonRpcRemote    tcp://127.0.0.1:8271    MyLibrary
...            greeting=hello    rpc_timeout=20    rpc_scope=TEST
```

### Session scope (`rpc_scope`)

`rpc_scope` controls the lifetime of the remote session — the connection and the imported library instance:

*   `TEST`: a fresh session is started and torn down for each test case.
*   `SUITE` (default): one session per suite.
*   `GLOBAL`: a single session is shared across the entire run.

### Log forwarding and error handling

*   **Log forwarding:** log messages emitted by a keyword on the server are forwarded to the client *while the keyword runs* and appear in the normal Robot Framework log.
*   **Errors:** if a remote keyword fails, the failure propagates to the client as a keyword failure, so the usual Robot Framework mechanisms work:

    ```robot
    Run Keyword And Expect Error    *boom*    Fail With    boom
    ```

### Server

The simplest option is the ready-made server package, which hosts your existing Robot Framework libraries without code changes:

```bash
pip install robotframework-jsonrpcremote-server
```

The positional `LIBRARY` arguments are an optional **allowlist** (scoped imports), so you can start the server with one, several, or no libraries:

```bash
# Restrict to a single library
robot-jsonrpcremote-server --port 8271 MyLibrary

# Allow several libraries (the first one is used as the default when a
# client connects without specifying library_name)
robot-jsonrpcremote-server --port 8271 MyLibrary OtherLibrary

# No allowlist: clients may import any library by name (library_name required)
robot-jsonrpcremote-server --port 8271
```

When an allowlist is given, clients may only import those libraries — a request for any other name is rejected. Libraries must be importable by the server; use `--pythonpath` to add directories (see the [end-to-end example](#end-to-end-example) below).

See [`packages/server`](packages/server) for all CLI options. For a hand-written server, check the `examples/simple-robot-jsonrpcserver` directory in this repository.

### End-to-end example

Define a regular Robot Framework library:

```python
# MyLibrary.py
class MyLibrary:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"
```

Start the ready-made server and make the library importable with `--pythonpath`:

```bash
robot-jsonrpcremote-server --pythonpath . --port 8271 MyLibrary
```

Then use it from a Robot Framework suite:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=MyLibrary

*** Test Cases ***
Greet Returns A Greeting
    ${greeting}=    Greet    World
    Should Be Equal    ${greeting}    Hello, World!
```

### stdio transport (single client, no network port)

Instead of TCP, the client can launch the server as a subprocess and talk to it over its stdin/stdout via a `stdio:<command>` URI (POSIX only) — handy for a self-contained, single-client setup without a network port:

```robot
*** Settings ***
Library    JsonRpcRemote    stdio:robot-jsonrpcremote-server --stdio --pythonpath . MyLibrary    library_name=MyLibrary
```

The client spawns the server, runs the suite over the pipe, and reaps the process on teardown. In stdio mode the server's stdout carries the JSON-RPC frames, so hosted keyword libraries must not write to stdout (`print`) — use stderr or Robot's logging.

## License

This project is licensed under the Apache-2.0 License.
