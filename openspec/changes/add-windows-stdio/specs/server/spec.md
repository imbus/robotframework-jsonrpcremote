# Spec Delta

## ADDED Requirements

### Requirement: stdio mode works on Windows

On Windows, the server SHALL serve one client over its stdin and stdout in stdio mode if both are overlapped pipes, as a client creates them that starts the server with `create_stdio_subprocess()`. The requirements for stdio mode SHALL hold there as on other platforms.

#### Scenario: Keywords and the moved streams

- **WHEN** a client on Windows starts the server in stdio mode, and a keyword starts a child process that writes to stdout and reads stdin
- **THEN** the keyword call returns its result, the next keyword call works, and the text appears on the server's stderr

#### Scenario: End of the input

- **WHEN** the client closes the server's stdin
- **THEN** the server stops and exits with exit code 0

### Requirement: On Windows stdio mode needs overlapped pipes

On Windows, the server in stdio mode SHALL treat a stdin or stdout that is not an overlapped pipe as a failed start, with an error stating that stdio on Windows needs overlapped pipes and naming the stream.

#### Scenario: Pipes that subprocess creates

- **WHEN** the server is started in stdio mode with `subprocess.PIPE` for stdin and stdout
- **THEN** the start fails with that error, naming stdin, and the process exits with exit code 1

#### Scenario: Null device on stdin

- **WHEN** the server is started in stdio mode with the null device as stdin
- **THEN** the start fails with that error, and the process exits with exit code 1

#### Scenario: Regular file on stdin

- **WHEN** the server is started in stdio mode with a regular file as stdin
- **THEN** the start fails with the error stating that stdio mode needs a stdin that can be watched, as on other platforms
