## ADDED Requirements

### Requirement: An invalid value from the environment is a usage error

When an environment variable that sets the default of an option holds a value that the option does not take, the server SHALL end with a usage error that names the option and the value, as for that value on the command line, and exit with exit code 2 before it starts, without a traceback. The reserved mode `pipe` SHALL still be refused as not supported yet. A value on the command line SHALL take precedence over the environment variable, also over an invalid value.

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
- **AND** the error does not say that the mode is not supported yet
- **AND** it exits with exit code 2, without a traceback

#### Scenario: The reserved mode from the environment

- **WHEN** the server is started with `ROBOT_JSONRPC_MODE=pipe` and without a mode option
- **THEN** it ends with a usage error that says that the mode `pipe` is not supported yet, as for `--pipe`
- **AND** it exits with exit code 2

#### Scenario: The command line takes precedence over an invalid value

- **WHEN** the server is started with `ROBOT_JSONRPC_PORT=abc` and `ROBOT_JSONRPC_MODE=tpc`, and with `--port 9000` and `--stdio`
- **THEN** it takes the port 9000 and the mode `stdio`, without an error about the environment
