# robotframework-jsonrpcremote

[DRAFT]

A **Robot Framework Remote Library** implementation using **JSON-RPC 2.0**.

This project enables running Robot Framework keywords on a remote server using the standard **JSON-RPC 2.0** protocol. It serves as an alternative to the standard [Remote Library](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#remote-library-interface).

## Features

*   **JSON-RPC 2.0:** Built on the lightweight and widely supported standard protocol.
*   **Language Agnostic:** Servers can be implemented in any language that supports JSON-RPC 2.0 (e.g., Node.js, Java, C#, Go, Rust, ...).
*   **Transport:** Uses persistent connections. Currently **TCP** is supported. **WebSockets**, **Named Pipes**, **Unix Domain Sockets**, **Standard I/O (stdio)**, **Streamable HTTP**, and **SSL/TLS** encryption are in development.
*   **Multiplexing:** The architecture supports sharing a single physical connection for multiple library instances (Connection Multiplexing), reducing resource usage.
*   **Asynchronous:** Built on Python's `asyncio`.
*   **Bidirectional Communication:** Allows the server to send **log messages** and progress updates to the client *during* keyword execution.
*   **Dependency Isolation:** Enables running libraries in separate processes or containers.
*   **Multi-Library Support:** A single server instance can host multiple Robot Framework libraries.
*   **Robot Framework Integration:**
    *   Support for **argument conversion** and custom converters.
    *   **Dynamic Initialization** of libraries with arguments.
    *   **Error Handling** with traceback support and failure modes (Fatal, Continuable, Skip).

## Architecture

The project is organized as a monorepo managed by [uv](https://github.com/astral-sh/uv):

*   **`packages/protocol`**: Defines the JSON-RPC 2.0 protocol messages, data structures, and types.
*   **`packages/jsonrpcpeer`**: An asynchronous JSON-RPC 2.0 peer implementation using `asyncio`.
*   **`packages/server`**: Server runtime components to host library code.
*   **`src/JsonRpcRemote`**: The Robot Framework Client Library (Proxy).
*   **`examples/`**: Usage examples and integration tests.

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
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8888

*** Test Cases ***
Example Test
    ${result}=    Echo    Hello World
    Should Be Equal    ${result}    Hello World
```

**Arguments:**
*   `uri`: The address of the remote server (default: `tcp://127.0.0.1:8271`).
*   `library_name`: The name of the library to initialize on the remote server (optional).
*   `rpc_timeout`: Connection timeout in seconds (default: `10.0`).
*   `rpc_scope`: The scope of the remote session (`TEST`, `SUITE`, `GLOBAL`). Default is `SUITE`.
*   `*args`: Positional arguments passed to the remote library initialization.
*   `**kwargs`: Keyword arguments passed to the remote library initialization.

### Server

To implement a server, you can use the provided server packages.

For a complete runnable example, please check the `examples/simple-robot-jsonrpcserver` directory in this repository.

## Development

This project uses `uv` for dependency management.

1.  **Setup**: `uv sync --all-extras --all-packages --dev`
2.  **Run Tests**:
    *   Start simple example server: `uv run -m simple_robot_jsonrpcserver`
    *   Run tests: `uv run robotcode run`
3.  **Build**: `uv build --all-packages`

## License

This project is licensed under the Apache-2.0 License.
