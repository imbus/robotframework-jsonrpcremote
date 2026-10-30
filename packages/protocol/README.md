# robotframework-jsonrpcremote-protocol

This package defines the **JSON-RPC 2.0** protocol between the client library `JsonRpcRemote` ([robotframework-jsonrpcremote](https://pypi.org/project/robotframework-jsonrpcremote/)) and the server ([robotframework-jsonrpcremote-server](https://pypi.org/project/robotframework-jsonrpcremote-server/)): the method names and, as Python dataclasses, the parameters and results of every message. Both use it as the source of truth, and so can a server of your own.

> **Status: pre-alpha.** The project is under active development: interfaces can still change, and more features are coming. See [Status and roadmap](https://imbus.github.io/robotframework-jsonrpcremote/roadmap/).

**Specification:** the [protocol page](https://imbus.github.io/robotframework-jsonrpcremote/reference/protocol/) of the documentation describes every message and field, with a hand-written example server.

## Summary

*   **Framing:** each message is a `Content-Length` header, an empty line and the JSON content, as in the Language Server Protocol.
*   **Methods:**

    | Method                   | Type         | Sent by |
    | :----------------------- | :----------- | :------ |
    | `robot/initialize`       | request      | client  |
    | `robot/initialized`      | notification | client  |
    | `robot/import_library`   | request      | client  |
    | `robot/run_keyword`      | request      | client  |
    | `robot/log`              | notification | server  |
    | `robot/finalize_library` | request      | client  |
    | `robot/shutdown`         | request      | client  |
    | `robot/exit`             | notification | client  |

    `robot/trace` is defined but not used yet.
*   **Flow:** the client initializes the connection, imports one library and gets a token and the library definition, runs keywords with the token while the server sends log messages, and finally finalizes the library, shuts down and exits.
*   **Values:** keyword arguments, return values and argument defaults are JSON values; the protocol is language-agnostic by design. In addition, the Python implementation sends Python objects as pickles, which travel unchanged between Python peers; for now it does so for every value that is not a JSON scalar. Conventions that let other languages read these values are planned.

## Usage

End users do not use this package directly; it is a dependency of the client and the server.
