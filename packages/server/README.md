# robotframework-jsonrpcremote-server

A **Robot Framework remote server** that speaks **JSON-RPC 2.0**. It hosts regular Robot Framework libraries, without changes, for the client library `JsonRpcRemote` from [robotframework-jsonrpcremote](https://pypi.org/project/robotframework-jsonrpcremote/).

> **Status: pre-alpha.** The project is under active development: interfaces can still change, and more features are coming. See [Status and roadmap](https://imbus.github.io/robotframework-jsonrpcremote/roadmap/).

**Documentation:** <https://imbus.github.io/robotframework-jsonrpcremote/>

## Installation

```bash
pip install robotframework-jsonrpcremote-server
```

Requires **Python >= 3.12** and **Robot Framework >= 7.2**.

## Quick start

Start the server with the libraries that clients may import. It listens on `127.0.0.1:8271` by default, so only programs on the same machine can connect:

```bash
robot-jsonrpcremote-server --pythonpath . MyLibrary
```

Then import the library through `JsonRpcRemote` in a suite:

```robot
*** Settings ***
Library    JsonRpcRemote    uri=tcp://127.0.0.1:8271    library_name=MyLibrary
```

Instead of connecting over TCP, the client can also start the server itself and talk to it over its stdin and stdout, with a URI such as `stdio:robot-jsonrpcremote-server --stdio --pythonpath . MyLibrary` (POSIX only).

## More

*   [Server options](https://imbus.github.io/robotframework-jsonrpcremote/reference/server/): all options and environment variables, and how the server starts and stops.
*   [TCP and stdio](https://imbus.github.io/robotframework-jsonrpcremote/guides/tcp-and-stdio/), [several libraries on one server](https://imbus.github.io/robotframework-jsonrpcremote/guides/several-libraries/) and [the server in a container](https://imbus.github.io/robotframework-jsonrpcremote/guides/container/).

## License

Apache-2.0
