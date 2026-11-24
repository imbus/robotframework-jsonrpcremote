# Spec Delta

## ADDED Requirements

### Requirement: A server in Node.js can serve the protocol with a JSON-RPC library

The repository SHALL contain an example server in Node.js, in TypeScript that Node.js runs directly, built on the JSON-RPC library `vscode-jsonrpc`. It SHALL serve a whole session over TCP, over stdio and over a pipe, SHALL read no pickles, and SHALL answer a call before the handshake and an unknown keyword with the error codes of the reference server.

#### Scenario: A whole session over TCP

- **WHEN** the example server listens on `127.0.0.1:8271`, and a suite imports its library with `tcp://127.0.0.1:8271`
- **THEN** the keywords run and return their results, and the session ends with `robot/shutdown` and `robot/exit`

#### Scenario: Started by the client over a pipe

- **WHEN** a suite imports the library with a `pipe:` URI whose command starts the example server with `node`
- **THEN** the server connects to the address of its `--pipe=` argument, and the keywords run

#### Scenario: Started by the client over stdio

- **WHEN** a suite imports the library with a `stdio:` URI whose command starts the example server with `--stdio`
- **THEN** the keywords run over the stdin and stdout of the server

#### Scenario: A log message while a keyword runs

- **WHEN** a keyword of the example server sends a log message before it returns
- **THEN** the message is in the Robot Framework log of that keyword call

#### Scenario: A list as an argument

- **WHEN** a keyword whose argument the example declares as `list[int]` is called with the list `[1, 2, 39]`
- **THEN** the server gets the list as plain JSON, and the keyword returns `42`

#### Scenario: A keyword that fails

- **WHEN** a keyword of the example server fails
- **THEN** the call fails with the message of the server, and the next keyword call works

#### Scenario: No pickles

- **WHEN** a client sends `robot/initialize` to the example server
- **THEN** the capabilities in the answer state no `pickle_protocol`

#### Scenario: A call before the handshake

- **WHEN** a client imports a library or calls a keyword before `robot/initialized`
- **THEN** the server answers with the error code `-32000`

#### Scenario: A keyword that the library does not have

- **WHEN** a client calls a keyword that the library of the example server does not have
- **THEN** the server answers with the error code `-32001`
