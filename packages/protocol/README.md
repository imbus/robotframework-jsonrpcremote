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
    *   `library_name`: `str` (optional) - The name of the Robot Framework library to initialize on the server.
    *   `library_args`: `list` (optional) - Positional arguments to pass to the library constructor.
    *   `library_kw_args`: `dict` (optional) - Keyword arguments to pass to the library constructor.

*   **`InitializeResult`**
    *   `library_definition`: `LibraryDefinition` - The definition of the initialized library, including keywords.
    *   `capabilities`: `ServerCapabilities` (optional) - Capabilities provided by the server.
    *   `server_info`: `ServerInfo` (optional) - Information about the server (name, version).

*   **`ClientInfo` / `ServerInfo`**
    *   `name`: `str` - The name of the client or server.
    *   `version`: `str` - The version of the client or server.

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
    *   `name`: `str` - The name of the keyword to execute.
    *   `args`: `list` (optional) - A list of positional arguments to pass to the keyword.
    *   `kwargs`: `dict` (optional) - A dictionary of keyword arguments to pass to the keyword.

*   **`RunKeywordResult`**
    *   `result`: `AnyType` (optional) - The return value of the keyword execution.
    *   `error`: `RunKeywordError` (optional) - Error details if execution failed.

*   **`RunKeywordError`**
    *   `message`: `str` - The error message.
    *   `type`: `str` (optional) - The type/name of the exception (e.g., "ValueError", "AssertionError").
        *   If provided, the client should display the error as `Type: Message`.
        *   If omitted (or null), the client should display only the `Message` (equivalent to `ROBOT_SUPPRESS_NAME=True`).
    *   `traceback`: `str` (optional) - The stack trace of the error, useful for debugging.
    *   `mode`: `str` (optional) - The failure mode. Can be one of:
        *   `"CONTINUABLE"`: Maps to `ROBOT_CONTINUE_ON_FAILURE = True`.
        *   `"FATAL"`: Maps to `ROBOT_EXIT_ON_FAILURE = True`.
        *   `"SKIP"`: Maps to `ROBOT_SKIP_EXECUTION = True`.
        *   If omitted, it is treated as a standard failure.

### Logging

*   **`LogParams`**
    *   `message`: `str` - The log message content.
    *   `level`: `str` (optional) - The log level (e.g., "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FAIL").
    *   `html`: `bool` (optional) - Whether the message should be treated as HTML.
    *   `console`: `bool` (optional) - Whether the message should be printed to the console.
    *   `timestamp`: `str` (optional) - The timestamp of the log message.

## Methods

The following constants define the JSON-RPC method names:

| Constant | Method Name | Type | Params | Result |
| :--- | :--- | :--- | :--- | :--- |
| `INITIALIZE_REQUEST` | `initialize` | Request | `InitializeParams` | `InitializeResult` |
| `INITIALIZED_NOTIFICATION` | `initialized` | Notification | `InitializedParams` | - |
| `RUN_KEYWORD_REQUEST` | `run_keyword` | Request | `RunKeywordParams` | `RunKeywordResult` |
| `LOG_NOTIFICATION` | `log` | Notification | `LogParams` | - |
| `SHUTDOWN_REQUEST` | `shutdown` | Request | `ShutdownParams` | `ShutdownResult` |
| `EXIT_NOTIFICATION` | `exit` | Notification | - | - |

## Communication Flow

The typical communication lifecycle is as follows:

1.  **Connection**: The client establishes a connection to the server (e.g., via stdio or TCP or ...).
2.  **Initialization**:
    *   **Request**: The client sends an `initialize` request containing `InitializeParams`. This includes:
        *   `library_name`: The name of the library to load.
        *   `library_args` / `library_kw_args`: Arguments required to initialize the library instance.
    *   **Processing**: The server attempts to import and instantiate the requested library.
        *   During this phase, the server **may** send `log` notifications to the client. This is useful for reporting loading progress, deprecation warnings, or initialization errors that don't prevent the connection but should be visible to the user.
    *   **Response (Success)**: Upon successful loading, the server responds with `InitializeResult`. This contains the `LibraryDefinition`, which describes the library and lists all available keywords with their arguments and documentation.
    *   **Response (Failure)**: If the library cannot be initialized (e.g., module not found, exception during instantiation), the server responds with a JSON-RPC **Error**.
        *   The error object should contain a meaningful message explaining why the initialization failed.
        *   The client must handle this error (e.g., by stopping the execution) and should not send an `initialized` notification.
    *   **Confirmation**: The client processes the library definition (e.g., registering keywords in Robot Framework) and sends an `initialized` notification.
        *   **Purpose**: This signals the completion of the handshake. It confirms that the client is fully synchronized and ready.
        *   **Constraint**: The server **must not** process any `run_keyword` requests until this `initialized` notification is received. If a request is received beforehand, the server should respond with a JSON-RPC error (e.g., code `-32000`: Not initialized).
        *   **Timeout**: If the client fails to send the `initialized` notification within a reasonable timeframe (implementation specific), the server **may** terminate the connection to release resources.
3.  **Execution Loop**:
    *   When Robot Framework executes a keyword from the remote library, the client sends a `run_keyword` request.
    *   The server executes the keyword implementation.
    *   During execution, the server can send `log` notifications to stream log messages to the client.
    *   **Response**: The server sends a response back to the client. There are two distinct error categories:
        1.  **Runtime Errors (Keyword Failure)**: If the keyword execution fails (e.g., assertion error, exception in library code), the server returns a **successful** JSON-RPC response containing a `RunKeywordResult`.
            *   The `error` field of `RunKeywordResult` contains a `RunKeywordError` object with the error message and optional details (traceback, continuable, etc.).
            *   The client treats this as a failed keyword execution within the test (FAIL).
        2.  **Protocol/Resolution Errors**: If the request is invalid (e.g., keyword not found, invalid argument count/types), the server returns a **JSON-RPC Error**.
            *   Since standard JSON-RPC errors like `-32601` refer to the RPC method (`run_keyword`) itself, specific application error codes are defined for keyword resolution (using the implementation-defined server-error range `-32000` to `-32099`):
                *   `-32001`: Keyword not found.
                *   `-32002`: Argument mismatch (e.g., wrong number of arguments).
            *   The client treats this as an infrastructure/protocol failure.
4.  **Termination**:
    *   The client sends a `shutdown` request. This acts as the **finalization** step for the current library session.
        *   The server releases the library instance, cleans up resources (e.g., closes database connections, file handles), and responds.
    *   The client sends an `exit` notification.
        *   This signals the server to close the connection.
        *   If the server process was started by the client (e.g., via stdio), this notification instructs the server to terminate the process.

## Usage

This package is typically not used directly by end users, but serves as a dependency for:

*   `robotframework-jsonrpcremote` (Client)
*   `robotframework-jsonrpcremote-server` (Server)
