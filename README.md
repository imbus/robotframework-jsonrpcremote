# robotframework-jsonrpcremote

A modern alternative to Robot Framework's [Remote library](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#remote-library-interface), built on **JSON-RPC 2.0**: a simple, standardized protocol that every common programming language supports.

> **Status: pre-alpha.** The project is under active development: interfaces can still change, and more features are coming. [Status and roadmap](https://imbus.github.io/robotframework-jsonrpcremote/roadmap/) lists what works today and what is planned.

**Documentation:** <https://imbus.github.io/robotframework-jsonrpcremote/>

## Features

*   **Language-agnostic:** the protocol is JSON-RPC 2.0, which every common programming language supports, so a server that offers keywords can be written in any of them; with a JSON-RPC library, that takes only a few lines of code. Messages and values are JSON; between Python peers, Python objects also travel unchanged, as pickles.
*   **JSON-RPC 2.0** over one persistent connection per session, framed as in the Language Server Protocol.
*   **Both directions:** log messages of a remote keyword reach the Robot Framework log while the keyword runs.
*   **Transports:** TCP; stdio, where the client starts the server for a session and stops it again; named pipes, Unix domain sockets, WebSockets and Streamable HTTP; encryption with TLS.
*   **Almost any library, remote:** the server `robot-jsonrpcremote-server` makes Robot Framework libraries remote without code changes. Robot Framework itself imports and runs them, with its argument conversion and custom converters.
*   **Several libraries on one server**, which a suite imports by name.
*   **Library arguments from the suite**, converted on the server.
*   **Sessions** per test, suite or run, **detection of lost connections** and **connect retry**.
*   **Failures and timeouts:** continuable, fatal and skipped failures with the type and traceback of the error, and keyword timeouts with cancellation, including the test and keyword timeouts of Robot Framework.
*   **Dependency isolation:** libraries run in a process or container of their own, for example as a sidecar next to the tests.

[Why JsonRpcRemote](https://imbus.github.io/robotframework-jsonrpcremote/why-jsonrpcremote/) describes what it is for and what it does better than the Remote library.

## Requirements

*   Python >= 3.12
*   Robot Framework >= 7.2

## Installation

Install the client where the suites run and the server where the libraries run:

```bash
pip install robotframework-jsonrpcremote robotframework-jsonrpcremote-server
```

## Example

A regular Robot Framework library:

```python
# MyLibrary.py
from robot.api import logger


class MyLibrary:
    def greet(self, name: str) -> str:
        logger.info(f"Greeting {name}")
        return f"Hello, {name}!"
```

Start the server in the directory with `MyLibrary.py`. It listens on `127.0.0.1:8271`:

```bash
robot-jsonrpcremote-server --pythonpath . MyLibrary
```

Use the library from a suite:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=MyLibrary

*** Test Cases ***
Greet Returns A Greeting
    ${greeting}=    Greet    World
    Should Be Equal    ${greeting}    Hello, World!
```

[Getting started](https://imbus.github.io/robotframework-jsonrpcremote/getting-started/) runs this example step by step. The guides cover TCP and stdio, sessions, lost connections and connect retry, the server in a container, and several libraries on one server.

## Contributing

See [CONTRIBUTING.md](https://github.com/imbus/robotframework-jsonrpcremote/blob/main/CONTRIBUTING.md), which also describes the structure of the repository.

## License

This project is licensed under the Apache-2.0 License.
