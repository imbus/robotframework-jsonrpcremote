# jsonrpcpeer

A lightweight, asynchronous **JSON-RPC 2.0** peer implementation for Python, built on top of `asyncio`.

This package provides the core communication logic used by `robotframework-jsonrpcremote`, but it can be used independently to build custom JSON-RPC 2.0 clients and servers. The [documentation of robotframework-jsonrpcremote](https://imbus.github.io/robotframework-jsonrpcremote/) shows a Robot Framework remote server built on it, on its [protocol page](https://imbus.github.io/robotframework-jsonrpcremote/reference/protocol/).

> **Status: pre-alpha.** The project is under active development: interfaces can still change, and more features are coming. See [Status and roadmap](https://imbus.github.io/robotframework-jsonrpcremote/roadmap/).

## Features

*   **Standard Compliant:** Full JSON-RPC 2.0 support (Requests, Notifications, Batches, Errors).
*   **Asynchronous:** Built using Python's `asyncio` for high performance.
*   **Type Safe:** Uses Python type hints for automatic parameter deserialization.
*   **Endpoints:** One definition of an interface for both sides of a connection, which type checkers hold both sides to.
*   **Flexible:** Works with any `asyncio.StreamReader` and `asyncio.StreamWriter`.
*   **stdio:** `open_stdio_connection()` connects a process over its stdin and stdout, and keeps `print()` and child processes out of the connection; `create_stdio_subprocess()` starts a process with such a connection. Both work on Linux, macOS and Windows.
*   **Pipes:** `start_pipe_server()` and `open_pipe_connection()` listen on and connect to a named pipe on Windows and a Unix domain socket elsewhere; `create_pipe_subprocess()` starts a process with a connection over a pipe of its own, as an editor starts a language server.
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

You can register handlers using simple functions, or state an interface once and implement it in a class.

#### 1. Function-based Registration (Simple)

This approach is good for simple scripts or when you don't need complex parameter structures.

See [examples/simple_server.py](examples/simple_server.py) and [examples/simple_client.py](examples/simple_client.py).

#### 2. Endpoints (Recommended)

For larger applications, state an interface once, in a definition. One side of a connection implements it, the other side calls it. The name of each method on the wire and the types of its params and its result are written only here:

```python
from abc import abstractmethod
from dataclasses import dataclass

from jsonrpcpeer import JsonRpcEndpoint, rpc_notification, rpc_request


@dataclass
class AddParams:
    a: float
    b: float


@dataclass
class AddResult:
    result: float


@dataclass
class LogParams:
    message: str


class Calculator(JsonRpcEndpoint):
    @rpc_request("add")
    @abstractmethod
    async def add(self, params: AddParams) -> AddResult: ...


class CalculatorLog(JsonRpcEndpoint):
    @rpc_notification("log")
    @abstractmethod
    async def log(self, params: LogParams) -> None: ...
```

A method of a definition carries `rpc_request` or `rpc_notification`, is `async def` and takes one parameter, the params.

**Implementing it:** a subclass overrides the methods, without a mark of its own, and `attach_endpoint` registers them. If a method is missing, creating the object raises a `TypeError` that names it. Inside an endpoint, `self.remote(...)` calls the other side:

```python
class WorkingCalculator(Calculator):
    async def add(self, params: AddParams) -> AddResult:
        await self.remote(CalculatorLog).log(LogParams(message=f"Adding {params.a} and {params.b}"))
        return AddResult(result=params.a + params.b)


server_peer.attach_endpoint(WorkingCalculator())
```

**Calling it:** `remote` gives an object of the definition whose methods send, the same one each time for a definition on a peer. A request method waits for the response and converts its result to the return annotation; a notification method sends without waiting. Type checkers such as `mypy` and `pyright` see a `Calculator`, so they report params of the wrong type and methods that the definition does not have, and the calling project needs no setting for that:

```python
class PrintingLog(CalculatorLog):
    async def log(self, params: LogParams) -> None:
        print(params.message)


client_peer.attach_endpoint(PrintingLog())

result = await client_peer.remote(Calculator).add(AddParams(a=10, b=20))
print(result.result)  # 30.0
```

An error response raises a `JsonRpcResponseError`, and a closed connection a `JsonRpcConnectionClosedError`, as with `send_request` and `send_notification`.

*   **Several endpoints on one peer:** call `attach_endpoint` once for each, or let one class derive from several definitions. Two handlers for the same name on the wire raise `JsonRpcMethodAlreadyRegisteredError`. On the calling side, the definition selects the interface, as in `peer.remote(Calculator)` and `peer.remote(CalculatorLog)`. `remote` always goes to the other side, also when the peer implements that definition itself.
*   **Default implementations:** a marked method with a body and without `abstractmethod` answers unless a subclass overrides it. Through `remote`, it still goes to the other side.
*   **Without a separate definition:** a subclass of `JsonRpcEndpoint` can also carry marks on methods with a body, as in `@rpc_request("add")`, when only one side needs the method.

See [examples/class_based_api.py](examples/class_based_api.py), [examples/class_based_server.py](examples/class_based_server.py) and [examples/class_based_client.py](examples/class_based_client.py).

#### 3. Typed Registration

This example shows how to use typed handlers and clients.

See [examples/typed_server.py](examples/typed_server.py) and [examples/typed_client.py](examples/typed_client.py).

### Over stdin and stdout

A process that its client starts can serve that client over its own stdin and stdout. `open_stdio_connection()` returns a reader and a writer for them, as `asyncio.open_connection()` does for TCP:

```python
import asyncio

from jsonrpcpeer import JsonRpcPeer, open_stdio_connection


async def main() -> None:
    peer = JsonRpcPeer(*await open_stdio_connection())
    peer.attach_endpoint(WorkingCalculator())
    await peer.run()


asyncio.run(main())
```

The function also moves the standard streams out of the way of the messages, and there is no option to keep them. Afterwards, what the process, a C extension or a child process writes to stdout goes to stderr, and reading stdin gives the end of the input, so `print()` cannot corrupt the connection. If stdin cannot be watched for input, as a pipe or a socket can, or if stdin or stdout is closed, it raises a `RuntimeError` and leaves them as they are.

On Windows, stdin must be a pipe. The function uses an overlapped pipe through the I/O completion ports of the proactor event loop, the default event loop there, without a thread. A synchronous pipe, as `subprocess` creates it or VS Code for a debug adapter, gets a thread of its own for its direction.

Closing the writer ends the connection in both directions, and `writer.wait_closed()` waits for that, as with a socket.

The other side starts the process with `create_stdio_subprocess()`, which returns the process with a reader for its stdout and a writer for its stdin. Further arguments go to `asyncio.create_subprocess_exec()`:

```python
import sys

from jsonrpcpeer import JsonRpcPeer, create_stdio_subprocess


async def add_over_stdio() -> float:
    process, reader, writer = await create_stdio_subprocess(sys.executable, "calculator_server.py")
    client_peer = JsonRpcPeer(reader, writer)
    client_peer.attach_endpoint(PrintingLog())
    client_peer.start()
    result = await client_peer.remote(Calculator).add(AddParams(a=10, b=20))
    # The end of its input ends the process.
    await client_peer.stop()
    await process.wait()
    return result.result
```

On Windows, the process gets overlapped pipes, which a Python process can use without threads, and a console program gets no window of its own if the caller has no console. Closing the writer ends the input of the process; the reader ends when the process has closed its stdout.

### Over a pipe

A pipe connects processes on one machine: a named pipe on Windows, a Unix domain socket elsewhere. `start_pipe_server()` and `open_pipe_connection()` work as `asyncio.start_unix_server()` and `asyncio.open_unix_connection()` do, on every platform:

```python
import asyncio

from jsonrpcpeer import JsonRpcPeer, open_pipe_connection, start_pipe_server


async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    server_peer = JsonRpcPeer(reader, writer)
    server_peer.attach_endpoint(WorkingCalculator())
    await server_peer.run()


async def main() -> None:
    server = await start_pipe_server(serve, "calculator")
    async with server:
        await server.serve_forever()


async def add_over_a_pipe() -> float:
    client_peer = JsonRpcPeer(*await open_pipe_connection("calculator"))
    client_peer.attach_endpoint(PrintingLog())
    client_peer.start()
    result = await client_peer.remote(Calculator).add(AddParams(a=10, b=20))
    await client_peer.stop()
    return result.result
```

*   **Names:** on Windows, a bare name such as `calculator` means the named pipe `\\.\pipe\calculator`, and a name that starts with `\\` or `//` is used as written. Elsewhere, the name is the path of the socket file, relative to the working directory unless it is absolute; the platform allows 107 bytes on Linux and 103 on macOS. `pipe_address(name)` returns the address of a name.
*   **A name in use:** `start_pipe_server()` raises an `OSError` with `errno.EADDRINUSE` if a server listens on the name. Elsewhere than on Windows, it replaces a socket file on which nobody listens, as a server that was killed leaves it behind, and closing the server removes its socket file.
*   **Who can connect:** on Windows, the pipe gets the default security descriptor, so only the user who started the server, administrators and SYSTEM can write to it. Elsewhere, whoever may write to the socket file can connect; a directory that only you can enter keeps the others out.
*   **Errors** name the address, also the `FileNotFoundError` when nobody listens there.
*   **On Windows,** both functions need the proactor event loop, the default event loop there. `wait_closed()` of the server returns once the server is closed: unlike the server of asyncio, it does not wait for the connections that it has accepted, so close them yourself if you have to wait for them. After `close()`, a new connection waits while a connection that the server accepted is open, because the pipe is busy, and fails once those connections have ended.

A client can also start its server with a connection over a pipe of its own. `create_pipe_subprocess()` listens on a new address and starts the process with `--pipe=<address>` as its last argument, as `vscode-languageclient` starts a language server. It returns the process with a reader and a writer once the process has connected, and then stops listening, so that no other connection reaches the caller; on Windows, another connection waits while the first one is open, because the pipe is busy. Elsewhere than on Windows, the address lies in a new directory that only the current user can enter. Further arguments go to `asyncio.create_subprocess_exec()`, so stdin, stdout and stderr stay as the caller chooses:

```python
import sys

from jsonrpcpeer import JsonRpcPeer, create_pipe_subprocess


async def add_over_a_pipe_of_its_own() -> float:
    process, reader, writer = await create_pipe_subprocess(sys.executable, "calculator_server.py")
    client_peer = JsonRpcPeer(reader, writer)
    client_peer.attach_endpoint(PrintingLog())
    client_peer.start()
    result = await client_peer.remote(Calculator).add(AddParams(a=10, b=20))
    # The end of its connection ends the process.
    await client_peer.stop()
    await process.wait()
    return result.result
```

The process connects to the address after `--pipe=`:

```python
import asyncio
import sys

from jsonrpcpeer import JsonRpcPeer, open_pipe_connection


async def main() -> None:
    address = next(arg.removeprefix("--pipe=") for arg in sys.argv if arg.startswith("--pipe="))
    server_peer = JsonRpcPeer(*await open_pipe_connection(address))
    server_peer.attach_endpoint(WorkingCalculator())
    await server_peer.run()


asyncio.run(main())
```

If the process exits before it connects, the call raises a `ConnectionError` with its exit code. If the call is cancelled before, for example by `asyncio.wait_for()`, it kills the process. On Windows, a console program gets no window of its own if the caller has no console, as with `create_stdio_subprocess()`.

A process in another language connects with what its platform offers, such as `net.connect()` in Node. On Windows, a pipe opened for synchronous I/O, as `open()` in Python opens it, handles one operation at a time: a write waits until a pending read has returned. Such a process can read a request and then write its response. One that reads and writes at the same time has to open the pipe for overlapped I/O, as asyncio and Node do.

### Handler Signatures

Handlers can be registered with two types of signatures:

1.  **(params) -> result**: Simple handler receiving only parameters.
2.  **(peer, params) -> result**: Handler that also receives the `JsonRpcPeer` instance (useful for context or sending callbacks).

A handler can be an `async` function or a plain function. A plain function runs on the event loop and holds up the other messages while it runs, as does an `async` function without an `await`, so anything slow belongs in a thread or an executor. If a plain function returns an awaitable, the peer waits for it. A method of a definition stays `async def`, because a call over the connection always waits: type checkers report a plain method as an override of it, and `remote` refuses a definition with a plain method.

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

Requests you send fail with `JsonRpcConnectionClosedError`, a subclass of `ConnectionError`, once the connection closes, whether the remote side closed it, reading from it failed, or the peer was stopped. This applies to requests still waiting for a response and to requests and notifications sent afterwards, which fail immediately without being written. If reading from the connection failed, that error is attached as the exception's `__cause__`:

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
*   **Stopping:** `await peer.stop()` ends the peer at any time, also before or right after `start()`. Requests still waiting for a response fail with `JsonRpcConnectionClosedError`, and new requests and notifications are rejected. `stop()` does not wait for the writer to finish closing.
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
