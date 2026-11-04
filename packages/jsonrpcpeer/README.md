# jsonrpcpeer

A lightweight, asynchronous **JSON-RPC 2.0** peer implementation for Python, built on top of `asyncio`.

This package provides the core communication logic used by `robotframework-jsonrpcremote`, but it can be used independently to build custom JSON-RPC 2.0 clients and servers. The [documentation of robotframework-jsonrpcremote](https://imbus.github.io/robotframework-jsonrpcremote/) shows a Robot Framework remote server built on it, on its [protocol page](https://imbus.github.io/robotframework-jsonrpcremote/reference/protocol/).

> **Status: pre-alpha.** The project is under active development: interfaces can still change, and more features are coming. See [Status and roadmap](https://imbus.github.io/robotframework-jsonrpcremote/roadmap/).

## Features

*   **Standard Compliant:** Full JSON-RPC 2.0 support (Requests, Notifications, Batches, Errors).
*   **Asynchronous:** Built using Python's `asyncio` for high performance.
*   **Type Safe:** Uses Python type hints for automatic parameter deserialization.
*   **Flexible:** Works with any `asyncio.StreamReader` and `asyncio.StreamWriter`.
*   **Data Helpers:** Includes utilities for converting Python `dataclasses` to/from JSON.

## Protocol & Framing

While this library implements the JSON-RPC 2.0 protocol for the message payload, it uses a specific framing strategy for the transport layer, similar to the [Language Server Protocol (LSP)](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.18/specification/#headerPart) or V8 Inspector Protocol.

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
*   Header names are matched without regard to case, and the space after the colon is optional.
*   A message without a charset is read as UTF-8. With `JsonRpcPeer(reader, writer, default_encoding="latin-1")`, the peer sends in that charset and names it in a `Content-Type` header.

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
*   `dataclasses` and other classes with annotated fields
*   `list`, `dict` and the abstract types `Sequence`, `MutableSequence`, `Collection`, `Iterable` and `Mapping`, with their element types
*   `tuple`, as in `tuple[int, str]` and `tuple[int, ...]`, and named tuples
*   Unions, `Optional` and `Literal`
*   Enums
*   `Any`

## Advanced Topics

### Type Conversion & Validation

`jsonrpcpeer` leverages Python's type hints to ensure that the data received from the remote peer matches what your handler expects.

*   **Strict Types:** The incoming JSON types must match the Python type hints (e.g., `int` expects a JSON number, `str` expects a JSON string). The only conversion between them is from an integer to a `float`. A boolean is no number: `true` fits `bool`, but neither `int` nor `float`.
*   **Dataclasses:** You can define complex data structures using `dataclasses`. The library will automatically map the incoming JSON object to your dataclass fields, and ignores keys that the class does not have. An object only becomes a dataclass or another class with annotated fields; for any target other than those, a mapping type or `Any`, it is an error.
*   **Collections:** An abstract type such as `Sequence[int]` gives a `list`. `tuple[int, str]` checks the length and each position, `tuple[int, ...]` checks each element, and a named tuple takes an array by position. Sets are not supported as targets.
*   **Dict Keys:** The keys of an object are checked against the key type of a `dict[K, V]`. Keys in JSON are strings, so the key `"1"` does not fit `dict[int, V]`. An enum as the key type gives its members.
*   **Unions:** A union tries its types in order, and the first that fits wins. Among several classes, it picks the one whose required fields are all present and that has the most of the object's keys. If several have equally many, the values decide, so a field such as `kind: Literal["a"]` tells classes apart; if several still fit, it is an error. Next to a dict type, a class wins only if it knows all keys of the object and the values fit; otherwise the dict keeps them all.
*   **Validation:** If the incoming data cannot be converted to the specified type (e.g., missing fields in a dataclass, or wrong type), the library automatically responds with a JSON-RPC `Invalid Params` error (-32602).

### Error Handling

An error response is a `JsonRpcResponseError` in both directions. It has the fields `code`, `message` and `data`, and its text is `RPC Error <code>: <message>`. `JsonRpcErrorCode` holds the codes of JSON-RPC 2.0; you can use codes of your own as well.

A handler answers with an error by raising it, and a request that gets an error response fails with it. This is not a connection failure: the next request on the same connection gets its response.

```python
from typing import Any

from jsonrpcpeer import JsonRpcErrorCode, JsonRpcResponseError


async def divide(params: dict[str, Any]) -> float:
    if params["b"] == 0:
        raise JsonRpcResponseError(JsonRpcErrorCode.INVALID_PARAMS, "b must not be 0", {"b": params["b"]})
    return params["a"] / params["b"]


server.register_request_handler("divide", divide)

try:
    await client.send_request("divide", {"a": 1, "b": 0})
except JsonRpcResponseError as e:
    print(e)  # RPC Error -32602: b must not be 0
    print(e.code == JsonRpcErrorCode.INVALID_PARAMS, e.message, e.data)  # True b must not be 0 {'b': 0}
```

*   **Other exceptions:** any other exception in a request handler results in an `Internal Error` (-32603) with the exception message. The peer logs it at `ERROR` level with its traceback and the name of the method, on the logger `jsonrpcpeer.peer`. It does the same for an exception in a notification handler.
*   **Tracebacks:** error responses carry no traceback, because it would show your code and paths to the remote side. With `JsonRpcPeer(reader, writer, send_tracebacks=True)`, the peer puts it into `data` when it builds a response from an exception: another exception in a handler, params that cannot be converted, or a message that cannot be parsed. An error that a handler raises stays as it is.
*   **Responses that cannot be sent:** a result and the `data` of an error must be writable as JSON, and a response must not exceed `max_message_size`. Otherwise the request gets an `Internal Error` (-32603) with the reason instead, and the peer logs it. In a batch, this concerns only that one response. If the connection is gone when a response is written, the peer sends nothing more.
*   **Messages that cannot be read:** the connection stays open, and the peer goes on with the next message. A header part without a valid `Content-Length` gets no answer, and the bytes that follow are read as the next header part. A message with an unknown charset, or whose content is not valid in its charset or as JSON, gets a `Parse Error` (-32700) with `id: null`. A message above `max_message_size` is skipped and gets an `Invalid Request` (-32600) with `id: null`. Requests you have sent keep waiting for their responses, because the peer cannot tell which of them such a message belonged to.
*   **Problems that nobody gets an answer about:** the peer logs them at `ERROR` level on the logger `jsonrpcpeer.peer`, and hands their text to a callback, if you give it one with `JsonRpcPeer(reader, writer, on_problem=callback)`. An exception in the callback is logged. These are messages that cannot be read, invalid messages and responses, a failing notification handler, params of a notification that cannot be converted, and an error response with `id: null`.

Requests you send fail with `JsonRpcConnectionClosedError`, a subclass of `ConnectionError`, once the connection closes, whether the remote side closed it, reading from it failed, or the peer was stopped. This applies to requests still waiting for a response and to requests sent afterwards, which fail immediately without being written. If reading from the connection failed, that error is attached as the exception's `__cause__`:

```python
from jsonrpcpeer import JsonRpcConnectionClosedError

try:
    result = await peer.send_request("add", {"a": 1, "b": 2})
except JsonRpcConnectionClosedError as e:
    print(f"Connection lost: {e.__cause__ or 'closed by the remote side'}")
```

### Lifecycle

*   **Creating:** a peer can be created before an event loop runs; it binds to the loop that is running when it is first used, for example by `start()`.
*   **Starting:** `start()` starts reading from the connection in a background task and returns at once; `await peer.run()` starts the peer and waits until it has ended.
*   **Completion:** `peer.completion` is a future that resolves with `True` once the peer has ended, whether the remote side closed the connection or the peer was stopped. If reading from the connection failed, awaiting it raises that error instead.
*   **Stopping:** `await peer.stop()` ends the peer at any time, also before or right after `start()`. Requests still waiting for a response fail with `JsonRpcConnectionClosedError`, and new requests are rejected. `stop()` does not wait for the writer to finish closing.
*   **Closing the writer:** with `auto_close=True`, the default, the peer closes its writer when it ends. Pass `auto_close=False` to close the writer yourself.
*   **Memory:** a peer that has ended keeps nothing alive that refers back to it, so it is freed once your code no longer references it.

### Bidirectional Communication

JSON-RPC 2.0 is a peer-to-peer protocol. Although we often use the terms "Client" and "Server":
*   **Client:** Typically initiates the connection.
*   **Server:** Accepts the connection.

Once connected, **both** sides can send requests and notifications to the other. This is useful for:
*   **Server-side Events:** The server sending notifications to the client (e.g., log messages).
*   **Callbacks:** The server requesting information from the client during a procedure call.

## License

Apache-2.0
