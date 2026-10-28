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
*   Robot Framework >= 7.2

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
*   `rpc_timeout`: Connection timeout in seconds or as a Robot Framework time string such as `15s` (default: `10.0`).
*   `rpc_scope`: The scope of the remote session (`TEST`, `SUITE`, `GLOBAL`). Default is `SUITE`.
*   `rpc_connect_retry_timeout`: How long to keep trying to connect when the server is not reachable, in seconds or as a time string such as `1 minute` (default: `0`, no retry). See [Lost connections](#lost-connections).
*   `rpc_connect_retry_interval`: How long to wait between two connection attempts while retrying, in seconds or as a time string (default: `1.0`). Must be greater than 0 when retry is enabled.
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

The client's own options — `rpc_timeout`, `rpc_scope`, `rpc_connect_retry_timeout` and `rpc_connect_retry_interval` — are consumed by `JsonRpcRemote` itself and are **not** forwarded to the remote library, so you can mix them freely with the library's named init arguments:

```robot
*** Settings ***
Library    JsonRpcRemote    tcp://127.0.0.1:8271    MyLibrary
...            greeting=hello    rpc_timeout=20    rpc_scope=TEST
...            rpc_connect_retry_timeout=1 minute    rpc_connect_retry_interval=2s
```

An option value that is not a number of seconds or a time string, or that is negative, makes the library import fail with an error that names the option.

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

### Lost connections

If the connection of a session ends without the client closing it, for example because the server crashed, was stopped or its container restarted, the client detects it. Every following keyword call in that session fails with:

```text
ConnectionError: Connection to 'tcp://127.0.0.1:8271' was lost: the connection was closed by the server
```

The cause is "the connection was closed by the server" when the server closed the connection cleanly. Otherwise it is the type and message of the error that ended the connection, for example `ConnectionResetError: [Errno 104] Connection reset by peer`. For a `stdio:` URI, the exit code of the server process is added, for example `(server process exited with code 3)`.

A keyword that is running when the connection is lost fails with:

```text
ConnectionError: Connection to 'tcp://127.0.0.1:8271' was lost while running keyword 'My Keyword': the connection was closed by the server
```

The client does not send that keyword again, since the server may already have run it.

Without connect retry, the client does not reconnect on its own. The lost session is kept until it ends according to `rpc_scope`, and the first keyword call after that starts a new session, which connects again and imports the remote library anew. With `rpc_scope=TEST`, only the rest of the current test fails; with `GLOBAL`, every later call of the run fails. Ending a session on the client side, at the end of its `rpc_scope`, is never reported as a lost connection.

#### Connect retry

Connect retry lets the client wait for a server that is not reachable yet, for example while its container restarts. It is off by default; enable it with `rpc_connect_retry_timeout`:

```robot
*** Settings ***
Library    JsonRpcRemote    tcp://127.0.0.1:8271    MyLibrary
...            rpc_connect_retry_timeout=1 minute    rpc_connect_retry_interval=2s
```

With connect retry, a failed connection attempt is repeated every `rpc_connect_retry_interval` until it succeeds or `rpc_connect_retry_timeout` has passed. This applies to every connection: at the library import, when a new session starts, and when the client replaces a lost session. Each attempt is still limited by `rpc_timeout`.

If the time passes without a connection, the call fails with an error such as:

```text
ConnectionError: Could not connect to 'tcp://127.0.0.1:8271' within 1 minute (31 attempts): ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 8271)
```

The client waits like that only once per outage: until a connection succeeds again, every further call makes a single attempt and fails right away if the server is still unreachable. After the next successful connection, a new outage gets the full time again. A connection that needed more than one attempt is logged at INFO level.

After a lost connection, the next keyword call replaces the session: it connects again and imports the remote library anew. The client then logs a warning such as:

```text
Connection to 'tcp://127.0.0.1:8271' was lost: the connection was closed by the server. Reconnected after 12.4s (7 attempts); the remote library was imported again, so its server-side state was reset.
```

As the warning says, the new session starts with a new instance of the remote library on the server: whatever the library kept in memory, such as an open application or a login, is gone. A keyword that was running when the connection was lost still fails and is not sent again.

Robot Framework registers the remote library's keywords once, at the library import. After a reconnect, the client therefore compares the library definition, its keywords and their arguments, documentation and sources, with the one from the import. If the server came back with a different definition, for example after an update of the library, the call fails with:

```text
ConnectionError: Reconnected to 'tcp://127.0.0.1:8271', but the library definition changed since the library was imported (keywords added: New Keyword); the library cannot be used until its session ends according to rpc_scope.
```

Every further call fails the same way, without connecting, until the session ends according to `rpc_scope`. A new session after that is not compared.

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
