# Spec Delta

## ADDED Requirements

### Requirement: On Windows an overlapped pipe goes through I/O completion ports

On Windows, `open_stdio_connection()` SHALL use an overlapped pipe on stdin or stdout through the proactor event loop, without a thread. The requirements for the connection over stdin and stdout SHALL hold there as on other platforms.

#### Scenario: Large messages

- **WHEN** a process on Windows with overlapped pipes on stdin and stdout calls `open_stdio_connection()`, and 4 MiB are sent to it over its stdin, and it sends them back over the pair
- **THEN** all bytes arrive unchanged

#### Scenario: No thread for the streams

- **WHEN** such a process calls `open_stdio_connection()` and exchanges a message
- **THEN** the number of threads of the process is the same as before the call

### Requirement: On Windows a synchronous pipe gets a thread of its own

On Windows, `open_stdio_connection()` SHALL read a synchronous pipe on stdin in a thread of its own, and write a synchronous pipe on stdout in another, so that the event loop never waits for such a pipe. This SHALL work on any event loop. The requirements for the connection over stdin and stdout SHALL hold there as for overlapped pipes.

#### Scenario: Pipes that subprocess creates

- **WHEN** a process started with `subprocess.PIPE` for stdin and stdout calls the function, and 4 MiB are sent to it over its stdin, and it sends them back over the pair
- **THEN** all bytes arrive unchanged
- **AND** the process has two threads more than before the call

#### Scenario: Node's default pipes

- **WHEN** a process started by Node's `child_process.spawn()` without a `stdio` option, as VS Code starts a debug adapter, runs a `JsonRpcPeer` on the pair, and Node sends it a request
- **THEN** Node receives the response

#### Scenario: Only stdin is synchronous

- **WHEN** stdin is a synchronous pipe and stdout an overlapped pipe
- **THEN** the process has one thread more than before the call, and messages pass in both directions

#### Scenario: The other end reads slowly

- **WHEN** the process writes 4 MiB while the other end does not read for 2 seconds
- **THEN** a timer of the event loop that is due in that time runs on time
- **AND** all bytes arrive once the other end reads

#### Scenario: Closing ends the threads

- **WHEN** the process closes the writer and awaits `writer.wait_closed()`, while the other end keeps its end of stdin open and sends nothing
- **THEN** the reader sees the end of the stream, and both threads have ended within 1 second

#### Scenario: A child process does not wait for the next message

- **WHEN** the process starts a child process while the thread waits for input on stdin, and the next message comes only 5 seconds later
- **THEN** the child process has run and ended within 2 seconds

#### Scenario: Selector event loop

- **WHEN** the function is called on a selector event loop with synchronous pipes on stdin and stdout
- **THEN** messages pass in both directions

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

### Requirement: On Windows the connection is refused for a stdin that is no pipe, and for an overlapped pipe without a proactor

On Windows, `open_stdio_connection()` SHALL raise a `RuntimeError` that names the reason if stdin is not a pipe, or if stdin or stdout is an overlapped pipe while the running event loop is not a proactor event loop. It SHALL then leave stdin and stdout as they are.

#### Scenario: Null device on stdin

- **WHEN** stdin is the null device
- **THEN** the error states that stdio mode needs a stdin that can be watched for input, such as a pipe, and that stdin is a character device

#### Scenario: Console on stdin

- **WHEN** stdin is a console
- **THEN** the error states the same need, and that stdin is a character device

#### Scenario: Overlapped pipes on a selector event loop

- **WHEN** the function is called on a selector event loop, and stdin and stdout are overlapped pipes
- **THEN** the error states that stdio on Windows needs the proactor event loop for overlapped pipes

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
