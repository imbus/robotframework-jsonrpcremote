# Spec Delta

## ADDED Requirements

### Requirement: A process can connect over its stdin and stdout

The `jsonrpcpeer` package SHALL export the coroutine function `open_stdio_connection()`. It SHALL return an `asyncio.StreamReader` and an `asyncio.StreamWriter` for the stdin and stdout of the current process, which a `JsonRpcPeer` can use like the pair of any other connection.

#### Scenario: A peer answers a request

- **WHEN** a process runs a `JsonRpcPeer` on the pair from `open_stdio_connection()`, and the process that started it sends a request over the process's stdin
- **THEN** the handler of the peer runs, and the response arrives on the process's stdout

#### Scenario: Large messages

- **WHEN** 4 MiB are sent to the process over its stdin, and it sends them back over the pair
- **THEN** all bytes arrive unchanged

### Requirement: What is written to stdout appears on stderr

After `open_stdio_connection()` has returned, file descriptor 1 SHALL refer to the stderr of the process, and the connection SHALL use a private duplicate of the original stdout. Only what is written to the returned writer SHALL reach the original stdout. This has no option to turn it off.

#### Scenario: print

- **WHEN** the process calls `print()` without flushing
- **THEN** the text appears on stderr at the end of its line, while the process still runs
- **AND** it does not appear on the original stdout

#### Scenario: Direct write to file descriptor 1

- **WHEN** the process calls `os.write(1, ...)`, or writes to `sys.__stdout__`
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: Child process

- **WHEN** the process starts a child process that inherits stdout, with `subprocess` or `os.system()`, and the child writes to its stdout
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: Text buffered before the call

- **WHEN** `sys.stdout` still holds text that was not flushed when the process calls `open_stdio_connection()`
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: After the connection has closed

- **WHEN** the writer has been closed and the process calls `print()`
- **THEN** the text appears on stderr without an error

### Requirement: stdin no longer delivers the data of the connection

After `open_stdio_connection()` has returned, file descriptor 0 SHALL refer to the null device, and the connection SHALL use a private duplicate of the original stdin. Only the returned reader SHALL receive what arrives on the original stdin.

#### Scenario: Reading stdin in the process

- **WHEN** data for the connection is waiting on the original stdin and the process calls `input()`, `sys.stdin.read()` or `os.read(0, ...)`
- **THEN** `input()` raises `EOFError`, and the other two return nothing
- **AND** the returned reader still receives the data

#### Scenario: Reading stdin in a child process

- **WHEN** the process starts a child process that inherits stdin, and the child reads it
- **THEN** the child sees the end of its input at once
- **AND** the returned reader still receives the data

### Requirement: A child process does not keep the connection open

The private duplicates SHALL NOT be inherited by child processes, so that the other end of the connection sees its end when the process ends, even if a child process still runs.

#### Scenario: Process ends while a child process runs

- **WHEN** the process starts a child process that keeps running, and then exits
- **THEN** the reader at the other end of the process's stdout sees the end of the stream at once, and not when the child process ends

### Requirement: The connection is refused if stdin or stdout cannot be used

`open_stdio_connection()` SHALL raise a `RuntimeError` that names the reason if stdin cannot be watched for input, as a pipe or a socket can, or if stdin or stdout is closed. It SHALL then leave stdin and stdout as they are. A pipe whose writing end is already closed is a valid stdin.

#### Scenario: stdin is the null device

- **WHEN** stdin is `/dev/null`
- **THEN** the error states that stdio mode needs a stdin that can be watched for input, such as a pipe, and that stdin is a character device

#### Scenario: stdin is a regular file

- **WHEN** stdin is a regular file
- **THEN** the error states the same need, and that stdin is a regular file

#### Scenario: stdin is closed

- **WHEN** file descriptor 0 is closed
- **THEN** the error states the same need, and that stdin is closed

#### Scenario: stdout is closed

- **WHEN** file descriptor 1 is closed
- **THEN** the error states that stdio mode needs an open stdout

#### Scenario: The standard streams stay after a refusal

- **WHEN** the call has been refused because of stdin, and the process then writes to its stdout
- **THEN** the text appears on the original stdout

#### Scenario: stdin is a pipe that is already closed

- **WHEN** stdin is a pipe whose writing end is already closed
- **THEN** the call returns, and the reader sees the end of the stream

### Requirement: A closed stderr does not get in the way of the connection

If the stderr of the process is closed, `open_stdio_connection()` SHALL work as usual, with what is written to stdout discarded, and SHALL NOT let its private duplicates take the place of file descriptor 2.

#### Scenario: Process without a stderr

- **WHEN** file descriptor 2 is closed, the process calls `open_stdio_connection()` and then writes to its stdout
- **THEN** messages still pass in both directions, and only what is written to the returned writer reaches the original stdout
- **AND** a write to file descriptor 2 does not reach the connection

### Requirement: The pair from stdin and stdout closes like the pair of a socket

Closing the returned writer SHALL end the connection in both directions, and `writer.wait_closed()` SHALL wait for that. The end of the input SHALL leave the writer usable. An error that ends the connection SHALL NOT be reported as never retrieved.

#### Scenario: The process closes the writer

- **WHEN** the process writes data, calls `writer.close()` and awaits `writer.wait_closed()`
- **THEN** the wait returns, the data arrives on the original stdout, the other end sees the end of the stream, and the reader sees the end of the stream too

#### Scenario: The input ends first

- **WHEN** the other end closes the process's stdin, and the process then writes data and closes the writer
- **THEN** the reader sees the end of the stream, and the data arrives on the original stdout

#### Scenario: The other end goes away

- **WHEN** the other end closes the reading end of the process's stdout while the process keeps writing
- **THEN** `writer.drain()` raises a `ConnectionError`, and the reader sees the end of the stream
- **AND** asyncio reports no exception as never retrieved
