# robotframework-jsonrpcremote-protocol

This package defines the **communication contract** for the `robotframework-jsonrpcremote` ecosystem. It provides the formal specification of data structures, message types, and interaction flows used to execute Robot Framework keywords remotely via **JSON-RPC 2.0**.

## Purpose

The primary goal of this protocol is to decouple the Robot Framework execution environment (Client) from the keyword implementation (Server). This allows:
*   **Remote Execution**: Running keywords on different machines or containers.
*   **Language Independence**: While this package provides Python type definitions, the underlying JSON-RPC protocol allows servers to be implemented in any language (e.g., Node.js, Java, C#).
*   **Process Isolation**: Running libraries in separate processes to avoid dependency conflicts (e.g., conflicting Python dependencies).

This package serves as the **source of truth** for both the client (`robotframework-jsonrpcremote`) and the server (`robotframework-jsonrpcremote-server`) implementations, ensuring strict type compatibility and a consistent behavior.

## Key Differences from Standard Remote Server

While Robot Framework has a built-in Remote Library interface based on XML-RPC, this protocol introduces several modern enhancements:

*   **JSON-RPC 2.0**: Uses a lightweight, widely supported format instead of XML-RPC.
*   **Bidirectional Communication**: Allows the server to send notifications (like log messages) to the client *during* keyword execution, enabling real-time logging and progress reporting.
*   **Transport Agnostic**: Designed to work over any stream-based transport (TCP, Stdio, WebSockets), making it suitable for local process isolation (via Stdio) as well as distributed testing.
*   **Dynamic Initialization**: Supports passing arguments during the library initialization phase, allowing for flexible configuration of remote libraries.
*   **Argument Conversion & Custom Converters**: Fully supports Robot Framework's argument conversion system, including custom argument converters. Type information is preserved and transmitted, allowing the server to perform precise data validation and conversion even for custom types.
*   **Rich Error Handling**: Distinguishes between protocol errors and application errors, with support for rich traceback information and failure modes (Fatal, Continuable, Skip).

## Protocol Overview

The protocol is based on JSON-RPC 2.0.

It is important to note that this package **only describes the protocol** (data structures, message types, and flow). The underlying transport mechanism used to establish the connection and transmit messages is irrelevant to these definitions. The protocol can be implemented over **TCP, Named Pipes, WebSockets, Standard I/O (STDIO)**, or any other stream-based transport.

It defines a set of requests and notifications for:

1.  **Initialization**: Handshaking and exchanging capabilities.
2.  **Library Discovery**: The server sends the library definition (keywords, arguments) to the client.
3.  **Execution**: The client requests the server to run keywords.
4.  **Logging**: The server sends log messages back to the client during execution.
5.  **Shutdown**: Graceful termination.

## Data Types (Draft)

> **Note:** This section is currently a draft and subject to change as the implementation evolves.

Since JSON-RPC is based on JSON, all data types must be JSON-serializable.

*   **Simple Types**: `str`, `int`, `float`, `bool`, `null` (mapped to `None` in Python).
*   **Complex Types**: `list` (JSON Array), `dict` (JSON Object).

### Extended Type Serialization

To ensure consistent handling of types not natively supported by JSON, the following serialization conventions **must** be used by both client and server:

*   **Date/Time (`datetime`, `date`, `time`)**: Serialize as **ISO 8601** strings (e.g., `"2025-12-18T14:30:00+00:00"`).
*   **Binary Data (`bytes`, `bytearray`)**: Serialize as **Base64** encoded strings.
*   **Decimal (`decimal.Decimal`)**: Serialize as **strings** to preserve precision (e.g., `"123.45"` instead of `123.45`).
*   **UUID (`uuid.UUID`)**: Serialize as **strings** (e.g., `"123e4567-e89b-12d3-a456-426614174000"`).
*   **Path (`pathlib.Path`)**: Serialize as **strings** (using forward slashes `/` is recommended for cross-platform compatibility).
*   **Custom Objects**: Serialize as a `dict` (JSON Object).
    *   If the receiver needs to reconstruct the specific object type, the dictionary **should** include a special discriminator field, such as `__type__` or `_type`, containing the type name.
    *   Example: `{"__type__": "MyCustomObject", "id": 1, "name": "foo"}`.

### Type Resolution Strategy

Since type names are transmitted as strings (e.g., in `ArgumentDefinition.type`), implementations must map these strings back to actual language-specific types.

*   **Standard Types**: Implementations should automatically map common type names (e.g., `"str"`, `"int"`, `"bool"`, `"datetime"`, `"UUID"`) to their corresponding language types.
*   **Custom Types**: For custom objects, the type name should be the **Fully Qualified Name (FQN)** of the type (e.g., `package.module.ClassName`).
    *   **Server**: The server sends the FQN of the argument types.
    *   **Client**: The client uses standard language mechanisms (e.g., `importlib` in Python) to resolve the FQN back to the actual type class.

In the data structure definitions below, `AnyType` refers to any valid JSON type (simple or complex), including these serialized representations.

## Data Structures

The following data classes define the payload for requests and responses.

### Initialization

*   **`InitializeParams`**
    *   `capabilities`: `ClientCapabilities` (optional) - Capabilities provided by the client.
    *   `client_info`: `ClientInfo` (optional) - Information about the client (name, version).
    *   `initialization_options`: `AnyType` (optional) - User-provided options for the server.
    *   `trace`: `str` (optional) - The initial trace setting (e.g., "off", "messages", "verbose").

*   **`InitializeResult`**
    *   `capabilities`: `ServerCapabilities` (optional) - Capabilities provided by the server.
    *   `server_info`: `ServerInfo` (optional) - Information about the server (name, version).

*   **`ClientInfo` / `ServerInfo`**
    *   `name`: `str` - The name of the client or server.
    *   `version`: `str` - The version of the client or server.

*   **`ClientCapabilities`**
    *   `supports_log`: `bool` (optional) - Whether the client supports log notifications.
    *   `supports_trace`: `bool` (optional) - Whether the client supports trace notifications.

*   **`ServerCapabilities`**
    *   `support_exit`: `bool` (optional) - Whether the server supports the exit notification.
    *   `libraries`: `list[str]` (optional) - A list of available libraries on the server.

### Library Management

*   **`ImportLibraryParams`**
    *   `name`: `str` - The name of the library to import.
    *   `args`: `list` (optional) - Positional arguments to pass to the library constructor.
    *   `kw_args`: `dict` (optional) - Keyword arguments to pass to the library constructor.

*   **`ImportLibraryResult`**
    *   `token`: `str` - A unique token representing the imported library instance.
    *   `definition`: `LibraryDefinition` - The definition of the imported library.

*   **`FinalizeLibraryParams`**
    *   `token`: `str` - The token of the library to finalize.

*   **`FinalizeLibraryResult`**
    *   (Empty object)

### Library Definition

*   **`LibraryDefinition`**
    *   `name`: `str` - The name of the library.
    *   `keywords`: `list[KeywordDefinition]` - A list of keywords provided by the library.
    *   `doc`: `str` (optional) - Documentation for the library.
    *   `source`: `str` (optional) - Path to the library source file (if available).

*   **`KeywordDefinition`**
    *   `name`: `str` - The name of the keyword.
    *   `args`: `list[ArgumentDefinition]` - A list of arguments accepted by the keyword.
    *   `doc`: `str` (optional) - Documentation for the keyword.
    *   `tags`: `list[str]` (optional) - Tags associated with the keyword.
    *   `source`: `str` (optional) - Path to the keyword source file (if available).
    *   `lineno`: `int` (optional) - Line number where the keyword is defined.

*   **`ArgumentDefinition`**
    *   `name`: `str` - The name of the argument.
    *   `type`: `str` (optional) - The type of the argument (e.g., type hint).
    *   `default`: `AnyType` (optional) - The default value of the argument, if any.
    *   `required`: `bool` (optional) - Whether the argument is required (default: `true`). If `false`, `default` contains the default value (which may be `null`).
    *   `kind`: `str` (optional) - The kind of the argument. Can be one of:
        *   `"POSITIONAL_ONLY"`
        *   `"POSITIONAL_OR_NAMED"`
        *   `"VAR_POSITIONAL"` (`*args`)
        *   `"NAMED_ONLY"`
        *   `"VAR_NAMED"` (`**kwargs`)
    *   `doc`: `str` (optional) - Documentation for the argument.

### Execution

*   **`RunKeywordParams`**
    *   `library_token`: `str` - The token of the library instance to execute the keyword on.
    *   `name`: `str` - The name of the keyword to execute.
    *   `args`: `list` (optional) - A list of positional arguments to pass to the keyword.
    *   `kwargs`: `dict` (optional) - A dictionary of keyword arguments to pass to the keyword.

*   **`RunKeywordResult`**
    *   `result`: `AnyType` (optional) - The return value of the keyword execution.
    *   `error`: `RunKeywordError` (optional) - Error details if execution failed.

*   **`RunKeywordError`**
    *   `message`: `str` - The error message.
    *   `type`: `str` (optional) - The type/name of the exception (e.g., "ValueError", "AssertionError").
    *   `traceback`: `str` (optional) - The stack trace of the error.
    *   `mode`: `str` (optional) - The failure mode. Can be one of:
        *   `"CONTINUABLE"`
        *   `"FATAL"`
        *   `"SKIP"`

### Logging

*   **`LogParams`**
    *   `message`: `str` - The log message content.
    *   `level`: `str` (optional) - The log level (e.g., "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "CONSOLE", "HTML").
    *   `html`: `bool` (optional) - Whether the message should be treated as HTML.
    *   `console`: `bool` (optional) - Whether the message should be printed to the console.
    *   `timestamp`: `str` (optional) - The timestamp of the log message.

## Methods

The following constants define the JSON-RPC method names:

| Constant | Method Name | Type | Params | Result |
| :--- | :--- | :--- | :--- | :--- |
| `INITIALIZE_REQUEST` | `robot/initialize` | Request | `InitializeParams` | `InitializeResult` |
| `INITIALIZED_NOTIFICATION` | `robot/initialized` | Notification | `InitializedParams` | - |
| `IMPORT_LIBRARY_REQUEST` | `robot/import_library` | Request | `ImportLibraryParams` | `ImportLibraryResult` |
| `FINALIZE_LIBRARY_REQUEST` | `robot/finalize_library` | Request | `FinalizeLibraryParams` | `FinalizeLibraryResult` |
| `RUN_KEYWORD_REQUEST` | `robot/run_keyword` | Request | `RunKeywordParams` | `RunKeywordResult` |
| `LOG_NOTIFICATION` | `robot/log` | Notification | `LogParams` | - |
| `TRACE_NOTIFICATION` | `robot/trace` | Notification | `LogParams` | - |
| `SHUTDOWN_REQUEST` | `robot/shutdown` | Request | `ShutdownParams` | `ShutdownResult` |
| `EXIT_NOTIFICATION` | `robot/exit` | Notification | - | - |

## Communication Flow

The typical communication lifecycle is as follows:

1.  **Connection**: The client establishes a connection to the server.
2.  **Initialization**:
    *   **Request**: The client sends a `robot/initialize` request.
    *   **Response**: The server responds with `InitializeResult`, exchanging capabilities.
    *   **Notification**: The client sends `robot/initialized` to confirm readiness.
3.  **Library Import**:
    *   **Request**: The client sends `robot/import_library` with the library name and arguments.
    *   **Response**: The server initializes the library and returns `ImportLibraryResult` containing a `token` and the `LibraryDefinition`.
4.  **Execution Loop**:
    *   **Request**: The client sends `robot/run_keyword` with the `library_token`, keyword name, and arguments.
    *   **Execution**: The server executes the keyword on the instance identified by the token.
    *   **Logging**: The server may send `robot/log` notifications during execution.
    *   **Response**: The server returns `RunKeywordResult` (success or error).
5.  **Library Finalization**:
    *   **Request**: The client sends `robot/finalize_library` with the `token` when the library is no longer needed.
    *   **Response**: The server cleans up the library instance.
6.  **Termination**:
    *   **Request**: The client sends `robot/shutdown`.
    *   **Notification**: The client sends `robot/exit` to close the connection.

## Usage

This package is typically not used directly by end users, but serves as a dependency for:

*   `robotframework-jsonrpcremote` (Client)
*   `robotframework-jsonrpcremote-server` (Server)
