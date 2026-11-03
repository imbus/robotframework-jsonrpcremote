# Spec Delta

## ADDED Requirements

### Requirement: On Windows the connection over stdin and stdout uses overlapped pipes

On Windows, `open_stdio_connection()` SHALL use overlapped pipes on stdin and stdout through the proactor event loop, without a thread for the streams. The requirements for the connection over stdin and stdout SHALL hold there as on other platforms.

#### Scenario: Large messages

- **WHEN** a process on Windows with overlapped pipes on stdin and stdout calls `open_stdio_connection()`, and 4 MiB are sent to it over its stdin, and it sends them back over the pair
- **THEN** all bytes arrive unchanged

#### Scenario: No thread for the streams

- **WHEN** such a process calls `open_stdio_connection()` and exchanges a message
- **THEN** the number of threads of the process is the same as before the call

### Requirement: On Windows the moved streams also reach the standard handles

On Windows, the move of stdin and stdout SHALL also change the handles that `GetStdHandle()` returns, which is what native code and child processes use.

#### Scenario: Native write to the standard output handle

- **WHEN** code calls `WriteFile()` on the handle from `GetStdHandle(STD_OUTPUT_HANDLE)`
- **THEN** the text appears on stderr and not on the original stdout

#### Scenario: Child process that writes and reads

- **WHEN** the process starts a child process with `subprocess` or `os.system()` that writes to its stdout and reads its stdin
- **THEN** the text appears on stderr and not on the original stdout
- **AND** the child sees the end of its input at once
- **AND** the returned reader still receives the data of the connection

### Requirement: On Windows the connection is refused without overlapped pipes or a proactor

On Windows, `open_stdio_connection()` SHALL raise a `RuntimeError` that names the reason if stdin or stdout is not an overlapped pipe, or if the running event loop is not a proactor event loop. It SHALL then leave stdin and stdout as they are.

#### Scenario: Pipes that subprocess creates

- **WHEN** a process started with `subprocess.PIPE` for stdin and stdout calls the function
- **THEN** the error states that stdio on Windows needs overlapped pipes and that stdin is not one

#### Scenario: Only stdout is not overlapped

- **WHEN** stdin is an overlapped pipe and stdout is a pipe that `subprocess` created
- **THEN** the error states that stdio on Windows needs overlapped pipes and that stdout is not one

#### Scenario: Null device on stdin

- **WHEN** stdin is the null device
- **THEN** the error states that stdio on Windows needs overlapped pipes and that stdin is not one

#### Scenario: Selector event loop

- **WHEN** the function is called on a selector event loop
- **THEN** the error states that stdio on Windows needs the proactor event loop

### Requirement: A process can be started with a connection over its stdin and stdout

The `jsonrpcpeer` package SHALL export the coroutine function `create_stdio_subprocess(*argv, **kwargs)`. It SHALL start the process and return it with an `asyncio.StreamReader` for its stdout and an `asyncio.StreamWriter` for its stdin. On Windows, both SHALL be overlapped pipes, on other platforms ordinary pipes. Further arguments SHALL go to `asyncio.create_subprocess_exec()`.

#### Scenario: A process that uses the connection function

- **WHEN** a process started this way calls `open_stdio_connection()` and runs a `JsonRpcPeer`, and the caller sends a request over the returned pair
- **THEN** the caller receives the response

#### Scenario: A process with plain blocking reads and writes

- **WHEN** a process started this way reads `sys.stdin.buffer` and writes `sys.stdout.buffer` with one reader and one writer, without `open_stdio_connection()`
- **THEN** all bytes pass in both directions, 4 MiB included

#### Scenario: Further arguments

- **WHEN** the caller passes `stderr=asyncio.subprocess.PIPE` and `cwd`
- **THEN** the process runs in that directory, and the caller can read its stderr from the returned process

#### Scenario: Closing the writer

- **WHEN** the caller closes the writer
- **THEN** the process sees the end of its input
- **AND** the reader of the caller sees the end of the stream at the latest when the process has ended

#### Scenario: Command that cannot be started

- **WHEN** the command does not exist
- **THEN** the call raises `FileNotFoundError`, and on Windows no handle of the pipes stays open

### Requirement: On Windows a process started without a console opens no window

On Windows, `create_stdio_subprocess()` SHALL start the process without a window if the caller has no console, unless the caller passes `creationflags`. If the caller has a console, the process SHALL share it.

#### Scenario: Caller without a console

- **WHEN** a caller without a console starts a process
- **THEN** the process is started with the flag `CREATE_NO_WINDOW`

#### Scenario: Caller with a console

- **WHEN** a caller with a console starts a process
- **THEN** the process is started without that flag, so that it writes to that console and gets its Ctrl+C

#### Scenario: Caller passes creationflags

- **WHEN** a caller without a console passes `creationflags`
- **THEN** the process is started with exactly these flags
