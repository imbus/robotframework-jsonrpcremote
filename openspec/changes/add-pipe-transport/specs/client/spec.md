# Spec Delta

## ADDED Requirements

### Requirement: A pipe URI with a command starts the server and talks to it over a pipe

For a `pipe:<command>` URI, the client SHALL split the command as for `stdio:`, listen on a new pipe, start the command with `--pipe=<address>` as its last argument, and talk to the server over the first connection to that pipe. The requirements for sessions, lost connections and connect retry SHALL hold as for `stdio:`, and the client SHALL end the server with its session as for `stdio:`.

#### Scenario: Python server

- **WHEN** a suite uses a `pipe:` URI with `robot-jsonrpcremote-server` and a library, without a mode option
- **THEN** keywords run and return their results, log messages reach the Robot Framework log, and a failing keyword fails only its call

#### Scenario: Server in another language

- **WHEN** a suite uses a `pipe:` URI with a server written in Node that connects to the address of its `--pipe=` argument
- **THEN** keywords run and return their results, with a message of 1 MiB passing in both directions, on Linux, macOS and Windows

#### Scenario: Command with backslashes on Windows

- **WHEN** the URI on Windows is `pipe:C:\path\to\server.exe Lib`
- **THEN** the client starts `C:\path\to\server.exe` with the arguments `Lib` and `--pipe=<address>`

#### Scenario: Server that exits during a call

- **WHEN** the server process exits with exit code 3 during a keyword call
- **THEN** the call fails with the lost-connection error that names the exit code

#### Scenario: Server that exits while a child process runs

- **WHEN** a keyword starts a child process that keeps running for 15 seconds, and the next keyword ends the server process with exit code 3
- **THEN** that call fails in less than 10 seconds with the lost-connection error that names the exit code

#### Scenario: A server for each session

- **WHEN** a library with `rpc_scope=TEST` uses a `pipe:` URI
- **THEN** each test runs against a server process of its own, and that process has ended after the test

#### Scenario: Command that cannot be found

- **WHEN** the command of a `pipe:` URI does not exist
- **THEN** the import fails with an error that names the command and says that `pipe://<name>` connects to a server that listens on a pipe

#### Scenario: URI without a command

- **WHEN** the URI is `pipe:` with nothing after it
- **THEN** the import fails with an error that shows the form `pipe:<command>`

### Requirement: A server started over a pipe gets an empty stdin and writes to the stderr of the client

The client SHALL start the server of a `pipe:` URI with the null device as its stdin, and with its stdout going where the stderr of the client process goes, as its stderr does.

#### Scenario: A child process reads stdin

- **WHEN** a keyword starts a child process that inherits stdin and reads it
- **THEN** the child process sees the end of its input at once, and the next keyword call works

#### Scenario: Output of the server

- **WHEN** the server writes text to its stdout, with `os.write(1, ...)` or from a child process
- **THEN** the text appears on the stderr of the client process and not on its stdout

### Requirement: A pipe URI with a name connects to a server that listens on a pipe

For a `pipe://<name>` URI, the client SHALL connect, within `rpc_timeout`, to the pipe that the text after `pipe://` names. On Windows, a bare name SHALL mean `\\.\pipe\<name>`, elsewhere the path of a Unix domain socket, relative to the working directory unless it is absolute. Connect retry SHALL work as for `tcp://`.

#### Scenario: Server that listens on a pipe

- **WHEN** a suite uses `pipe://<name>`, and a server listens on that pipe with `--pipe-server <name>`
- **THEN** keywords run and return their results

#### Scenario: Two libraries on one server

- **WHEN** a suite imports two libraries with the same `pipe://` URI
- **THEN** the keywords of both run, each library over a connection of its own

#### Scenario: Nobody listens

- **WHEN** nobody listens on the pipe, and connect retry is off
- **THEN** the import fails with an error that names the pipe

#### Scenario: A server that starts later

- **WHEN** `rpc_connect_retry_timeout` is 10 seconds, and a server starts listening on the pipe 2 seconds after the import began
- **THEN** the import succeeds

#### Scenario: Absolute path

- **WHEN** a suite on Linux or macOS uses `pipe://` followed by an absolute path, such as `pipe:///tmp/jsonrpc/robot.sock`
- **THEN** the client connects to the socket file at that path

#### Scenario: URI without a name

- **WHEN** the URI is `pipe://` with nothing after it
- **THEN** the import fails with an error that shows the form `pipe://<name>`

### Requirement: A stdio URI has its command right after the colon

The client SHALL refuse a URI that starts with `stdio://`, with an error that says that the command follows `stdio:` directly, and SHALL start no process for it. For a URI with any other unknown scheme, the error SHALL name `tcp`, `pipe` and `stdio` as the supported schemes.

#### Scenario: stdio with two slashes

- **WHEN** the URI is `stdio://robot-jsonrpcremote-server --stdio MyLibrary`
- **THEN** the import fails with an error that shows `stdio:robot-jsonrpcremote-server --stdio MyLibrary` as the form to write, and no process is started

#### Scenario: Unknown scheme

- **WHEN** the URI is `http://127.0.0.1:8271`
- **THEN** the import fails with an error that names `tcp`, `pipe` and `stdio` as the supported schemes
