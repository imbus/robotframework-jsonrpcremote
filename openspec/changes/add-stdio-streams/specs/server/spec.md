# Spec Delta

## ADDED Requirements

### Requirement: In stdio mode only protocol messages reach the client

In stdio mode, what a library, a child process or Robot Framework writes to the server's stdout SHALL appear on the server's stderr and SHALL NOT reach the client as part of the connection. The connection SHALL keep working afterwards.

#### Scenario: Child process that writes to stdout

- **WHEN** a keyword starts a child process that inherits stdout and writes to it, with `subprocess` or `os.system()`
- **THEN** the keyword call returns its result, and the next keyword call works
- **AND** the text appears on the server's stderr

#### Scenario: Direct write to file descriptor 1

- **WHEN** a keyword calls `os.write(1, ...)`
- **THEN** the keyword call returns its result, and the next keyword call works
- **AND** the text appears on the server's stderr

#### Scenario: Console output of a library

- **WHEN** a keyword calls `logger.console()`
- **THEN** the keyword call returns its result, and the next keyword call works
- **AND** the text appears on the server's stderr

#### Scenario: Output after a keyword returned

- **WHEN** a thread that a keyword started prints after the keyword returned
- **THEN** the next keyword call works
- **AND** the text appears on the server's stderr

#### Scenario: print in a keyword

- **WHEN** a keyword calls `print()`
- **THEN** Robot Framework captures the text and logs it as usual, as it does over TCP

### Requirement: In stdio mode keywords see an empty stdin

In stdio mode, a keyword or a child process that reads stdin SHALL see the end of its input at once, and SHALL NOT receive any part of the connection's data.

#### Scenario: A keyword reads stdin

- **WHEN** a keyword calls `input()`
- **THEN** `input()` raises `EOFError`, and the next keyword call works

#### Scenario: A child process reads stdin

- **WHEN** a keyword starts a child process that inherits stdin and reads it
- **THEN** the child process sees the end of its input, and the next keyword call works

### Requirement: In stdio mode a child process does not hide the end of the server

If the server process ends while a child process that a keyword started still runs, the client SHALL see the end of the connection when the server process ends, and not when the child process ends.

#### Scenario: Server exits while a child process runs

- **WHEN** a keyword starts a child process that keeps running for 15 seconds, and the next keyword ends the server process with exit code 3
- **THEN** that call fails in less than 10 seconds with the lost-connection error that names the exit code
