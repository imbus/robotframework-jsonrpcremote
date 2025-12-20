# jsonrpcpeer

A lightweight, asynchronous **JSON-RPC 2.0** peer implementation for Python, built on top of `asyncio`.

This package provides the core communication logic used by `robotframework-jsonrpcremote`, but it can be used independently to build custom JSON-RPC 2.0 clients and servers.

## Features

*   **Standard Compliant:** Full JSON-RPC 2.0 support (Requests, Notifications, Errors).
*   **Asynchronous:** Built using Python's `asyncio` for high performance.
*   **Type Safe:** Uses Python type hints for automatic parameter deserialization.
*   **Flexible:** Works with any `asyncio.StreamReader` and `asyncio.StreamWriter`.
*   **Data Helpers:** Includes utilities for converting Python `dataclasses` to/from JSON.

## Protocol & Framing

While this library implements the JSON-RPC 2.0 protocol for the message payload, it uses a specific framing strategy for the transport layer, similar to the [Language Server Protocol (LSP)](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#headerPart) or V8 Inspector Protocol.

Each message consists of two parts:
1.  **Header Part**: Contains the `Content-Length` header.
2.  **Content Part**: The actual JSON-RPC message.

Example:
```text
Content-Length: 45\r\n
\r\n
{"jsonrpc": "2.0", "method": "ping", "id": 1}
```

*   The headers are encoded in ASCII.
*   The headers are separated from the content by `\r\n\r\n`.
*   Currently, only `Content-Length` and `Content-Type` (for charset) are supported/parsed.

### Why use headers?

Stream-based transports (like TCP, pipes, or standard I/O) transmit data as a continuous stream of bytes rather than distinct messages. To correctly separate messages (framing), the receiver needs to know exactly where one message ends and the next begins.

While some implementations rely on newlines (which breaks with pretty-printed JSON) or try to parse balanced braces (which is complex and slow), using a `Content-Length` header is a robust and standard approach (used by HTTP and LSP) to determine the exact size of the message payload before reading it.

## Installation

```bash
pip install jsonrpcpeer
```

## Usage

You can find complete examples in the [examples](examples/) directory.

### Creating a Server

You can register handlers using simple functions or organize them in a class using decorators.

#### 1. Function-based Registration (Simple)

This approach is good for simple scripts or when you don't need complex parameter structures.

See [examples/simple_server.py](examples/simple_server.py) and [examples/simple_client.py](examples/simple_client.py).

#### 2. Class-based Registration (Recommended)

For larger applications, use classes and `dataclasses` to define your API. This example also demonstrates bidirectional communication (server calling client).

See [examples/class_based_server.py](examples/class_based_server.py) and [examples/class_based_client.py](examples/class_based_client.py).

#### 3. Typed Registration

This example shows how to use typed handlers and clients.

See [examples/typed_server.py](examples/typed_server.py) and [examples/typed_client.py](examples/typed_client.py).

### Handler Signatures

Handlers can be registered with two types of signatures:

1.  **(params) -> result**: Simple handler receiving only parameters.
2.  **(peer, params) -> result**: Handler that also receives the `JsonRpcPeer` instance (useful for context or sending callbacks).

The `params` argument type annotation is used to validate and convert the incoming JSON data. It supports:
*   Primitive types (`str`, `int`, `bool`, `float`)
*   `dataclasses`
*   `dict`, `list`
*   `Any`

## Advanced Topics

### Type Conversion & Validation

`jsonrpcpeer` leverages Python's type hints to ensure that the data received from the remote peer matches what your handler expects.

*   **Strict Types:** The library generally expects the incoming JSON types to match the Python type hints (e.g., `int` expects a JSON number, `str` expects a JSON string).
*   **Dataclasses:** You can define complex data structures using `dataclasses`. The library will automatically map the incoming JSON object to your dataclass fields.
*   **Validation:** If the incoming data cannot be converted to the specified type (e.g., missing fields in a dataclass, or wrong type), the library automatically responds with a JSON-RPC `Invalid Params` error (-32602).

### Error Handling

Exceptions raised within your request handlers are automatically caught and translated into JSON-RPC Error responses.

*   **Standard Exceptions:** Any unhandled exception results in an `Internal Error` (-32603) with the exception message.
*   **Custom Errors:** You can raise `JsonRpcError` (or subclasses) to return specific error codes and data to the client.

### Bidirectional Communication

JSON-RPC 2.0 is a peer-to-peer protocol. Although we often use the terms "Client" and "Server":
*   **Client:** Typically initiates the connection.
*   **Server:** Accepts the connection.

Once connected, **both** sides can send requests and notifications to the other. This is useful for:
*   **Server-side Events:** The server sending notifications to the client (e.g., progress updates, log messages).
*   **Callbacks:** The server requesting information from the client during a procedure call.

## License

Apache-2.0
