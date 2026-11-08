# Spec Delta

## ADDED Requirements

### Requirement: In pipe mode the server serves the client whose pipe it connects to

With `--pipe <name>`, `--pipe=<name>`, or `--mode pipe` and `--pipe-name <name>`, the server SHALL connect to the pipe of that name, serve the client that listens there, and exit with exit code 0 when the connection ends. On Windows, a bare name SHALL mean `\\.\pipe\<name>`, elsewhere the path of a Unix domain socket. If nobody listens there, the start SHALL fail as a failed start, with an error that names the pipe.

#### Scenario: A client that listens on a pipe

- **WHEN** a client listens on a pipe and starts the server with `--pipe=<address>` as its last argument
- **THEN** the client imports a library, and its keywords run and return their results

#### Scenario: The end of the connection

- **WHEN** the client closes the connection
- **THEN** the server stops and exits with exit code 0

#### Scenario: Nobody listens on the pipe

- **WHEN** the server is started with `--pipe` and a name that nobody listens on
- **THEN** the start fails with an error that names the pipe
- **AND** the process exits with exit code 1 without stating that it is up and running

#### Scenario: The name as the next argument

- **WHEN** the server is started with `--pipe <name>` instead of `--pipe=<name>`
- **THEN** it connects to the same pipe

### Requirement: In pipe-server mode the server listens on a pipe for any number of clients

With `--pipe-server <name>`, or `--mode pipe-server` and `--pipe-name <name>`, the server SHALL listen on the pipe of that name, with the names of pipe mode, and serve any number of clients until it is stopped, as in TCP mode. If the name is in use, the start SHALL fail as a failed start, with an error that names the pipe. When it stops on Linux or macOS, it SHALL remove its socket file.

#### Scenario: Two clients at once

- **WHEN** two clients connect to the server at the same time and import a library
- **THEN** the keywords of both run and return their results

#### Scenario: The log names the pipe

- **WHEN** the server is started with `--pipe-server robot`
- **THEN** its log names the pipe it listens on: `\\.\pipe\robot` on Windows, `robot` elsewhere

#### Scenario: The name is in use

- **WHEN** the server is started with `--pipe-server` and the name of a pipe that another server listens on
- **THEN** the start fails with an error that names the pipe
- **AND** the process exits with exit code 1 without stating that it is up and running
- **AND** the other server still accepts clients

#### Scenario: Stopping

- **WHEN** the server on Linux or macOS gets SIGINT or SIGTERM while a client is connected
- **THEN** it closes the connection and exits with exit code 0
- **AND** its socket file is gone

### Requirement: A value from the environment that its option does not take is a usage error

When an environment variable that sets the default of an option holds a value that the option does not take, the server SHALL end with a usage error that names the option and the value, as for that value on the command line, and exit with exit code 2 before it starts, without a traceback. A value on the command line SHALL take precedence over the environment variable, also over an invalid value.

#### Scenario: The port from the environment is not a number

- **WHEN** the server is started with `ROBOT_JSONRPC_PORT=abc` and without `--port`
- **THEN** it ends with a usage error that names `--port` and `abc`
- **AND** it exits with exit code 2, without a traceback and without stating that it is up and running

#### Scenario: A valid port from the environment is used

- **WHEN** the server is started with `ROBOT_JSONRPC_PORT=9001` and without `--port`
- **THEN** it takes the port 9001 as a number, as for `--port 9001`

#### Scenario: The mode from the environment is unknown

- **WHEN** the server is started with `ROBOT_JSONRPC_MODE=tpc` and without a mode option
- **THEN** it ends with a usage error that names `--mode` and `tpc` and lists the modes, as for `--mode tpc`
- **AND** it exits with exit code 2, without a traceback

#### Scenario: A pipe mode from the environment

- **WHEN** the server is started with `ROBOT_JSONRPC_MODE=pipe-server` and `ROBOT_JSONRPC_PIPE_NAME=<name>`, and without a mode option
- **THEN** it listens on that pipe, as for `--pipe-server <name>`

#### Scenario: The command line takes precedence over an invalid value

- **WHEN** the server is started with `ROBOT_JSONRPC_PORT=abc` and `ROBOT_JSONRPC_MODE=tpc`, and with `--port 9000` and `--stdio`
- **THEN** it takes the port 9000 and the mode `stdio`, without an error about the environment

## REMOVED Requirements

### Requirement: An invalid value from the environment is a usage error

**Reason**: It refused the mode `pipe` from the environment as reserved, and this change implements that mode.

**Migration**: The requirement A value from the environment that its option does not take is a usage error states the same rule without the reserved mode, and its scenario A pipe mode from the environment replaces the one for the reserved mode.
