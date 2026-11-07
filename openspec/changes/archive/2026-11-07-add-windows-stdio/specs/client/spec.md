# Spec Delta

## ADDED Requirements

### Requirement: The stdio transport works on Windows

On Windows, the client SHALL start the server of a `stdio:` URI and talk to it over its stdin and stdout, as on other platforms, with the requirements for sessions, lost connections and connect retry holding there too.

#### Scenario: Python server

- **WHEN** a suite on Windows uses a `stdio:` URI with `robot-jsonrpcremote-server --stdio`
- **THEN** keywords run and return their results, log messages reach the Robot Framework log, and a failing keyword fails only its call

#### Scenario: Server in another language

- **WHEN** a suite uses a `stdio:` URI with a server written in Node that reads its stdin and writes its stdout with one reader and one writer
- **THEN** keywords run and return their results, with a message of 1 MiB passing in both directions
- **AND** this holds on Linux and macOS as well

#### Scenario: Server that exits during a call

- **WHEN** the server process exits with exit code 3 during a keyword call
- **THEN** the call fails with the lost-connection error that names the exit code

#### Scenario: Wrapper script

- **WHEN** the command of the `stdio:` URI is a `.cmd` file that starts the server
- **THEN** keywords run and return their results

### Requirement: On Windows a backslash in a stdio command is an ordinary character

On Windows, the client SHALL treat a backslash in the command of a `stdio:` URI as an ordinary character, while quotes still group an argument. On other platforms, the client SHALL go on splitting the command as a POSIX shell does.

#### Scenario: Path with backslashes

- **WHEN** the URI is `stdio:C:\path\to\python.exe -m robot_jsonrpcremote_server --stdio Lib`
- **THEN** the client starts `C:\path\to\python.exe` with the remaining arguments

#### Scenario: Quoted path with a space

- **WHEN** the URI is `stdio:"C:\Program Files\tool\server.exe" --stdio`
- **THEN** the client starts `C:\Program Files\tool\server.exe` with the argument `--stdio`

#### Scenario: Backslash on POSIX

- **WHEN** the URI on a POSIX system is `stdio:server my\ library`
- **THEN** the client starts `server` with the single argument `my library`, as before

### Requirement: On Windows a session does not depend on the event loop policy

On Windows, the client SHALL run its session on a proactor event loop, whatever event loop policy the process has set.

#### Scenario: A library has set the selector policy

- **WHEN** the process has set `asyncio.WindowsSelectorEventLoopPolicy`, and a suite uses a `stdio:` URI
- **THEN** the session starts, and keywords run and return their results
