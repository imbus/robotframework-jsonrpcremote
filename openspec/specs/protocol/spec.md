# protocol Specification

## Purpose

Defines how the package `robotframework-jsonrpcremote-protocol` states both sides of the Robot protocol, so that clients and servers in Python share one definition of the name and the types of each method.

## Requirements

### Requirement: The protocol package defines the methods of a server

The module `robot_jsonrpcremote_protocol` SHALL export a definition `ServerEndpoint` with one method for each message that a client sends. Each method SHALL carry the name of the message on the wire and the types of its params and its result.

#### Scenario: Requests to the server

- **WHEN** a client calls `initialize`, `import_library`, `run_keyword`, `finalize_library` or `shutdown` through `ServerEndpoint`
- **THEN** the server gets the request `robot/initialize`, `robot/import_library`, `robot/run_keyword`, `robot/finalize_library` or `robot/shutdown`
- **AND** the call returns an `InitializeResult`, `ImportLibraryResult`, `RunKeywordResult`, `FinalizeLibraryResult` or `ShutdownResult`

#### Scenario: Notifications to the server

- **WHEN** a client calls `initialized`, `set_log_level` or `exit` through `ServerEndpoint`
- **THEN** the server gets the notification `robot/initialized`, `robot/set_log_level` or `robot/exit`

### Requirement: The protocol package defines the methods of a client

The module `robot_jsonrpcremote_protocol` SHALL export a definition `ClientEndpoint` with one method for each message that a server sends. Each method SHALL carry the name of the message on the wire and the type of its params.

#### Scenario: Log message to the client

- **WHEN** a server calls `log` through `ClientEndpoint` with a `LogParams`
- **THEN** the client gets the notification `robot/log` with these params

### Requirement: A server in Python can implement the server definition

A server in Python SHALL be able to implement the protocol by deriving from `ServerEndpoint` and attaching an object of that class to its peer. The package SHALL declare its dependency on `jsonrpcpeer`, which provides the definitions' base class.

#### Scenario: The example server implements it

- **WHEN** a client runs a whole session against the example server, from `robot/initialize` to `robot/exit`
- **THEN** the example server answers it through its implementation of `ServerEndpoint`

#### Scenario: The server package implements it

- **WHEN** a client connects to `robot-jsonrpcremote-server`
- **THEN** the object that answers the connection is a `ServerEndpoint`

#### Scenario: A method is missing

- **WHEN** a class derives from `ServerEndpoint` and leaves out `run_keyword`
- **THEN** creating an object of that class raises a `TypeError` that names `run_keyword`

#### Scenario: Installing the package

- **WHEN** `robotframework-jsonrpcremote-protocol` is installed
- **THEN** `jsonrpcpeer` is installed with it
