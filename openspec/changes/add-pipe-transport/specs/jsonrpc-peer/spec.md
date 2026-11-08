# Spec Delta

## ADDED Requirements

### Requirement: A pipe name means a named pipe on Windows and a socket file elsewhere

The `jsonrpcpeer` package SHALL export the function `pipe_address(name)`, and its functions for pipes SHALL resolve every name with it. On Windows, it SHALL return a name that starts with `\\` or `//` unchanged and put `\\.\pipe\` before any other name. On other platforms, it SHALL return the name unchanged, as the path of a Unix domain socket, relative to the working directory unless it is absolute. An empty name SHALL raise `ValueError`.

#### Scenario: Bare name on Windows

- **WHEN** `pipe_address("robot")` is called on Windows
- **THEN** it returns `\\.\pipe\robot`

#### Scenario: Full name on Windows

- **WHEN** a pipe server listens on `\\.\pipe\robot`, and processes on Windows connect with the name `\\.\pipe\robot` and with `//./pipe/robot`
- **THEN** the server accepts both connections

#### Scenario: A bare name never opens a file on Windows

- **WHEN** a regular file `robot` exists in the working directory on Windows, no server listens on `\\.\pipe\robot`, and a process connects with the name `robot`
- **THEN** the connection fails with `FileNotFoundError`, and the file stays closed

#### Scenario: Relative path on other platforms

- **WHEN** a pipe server on Linux or macOS listens on the name `robot.sock`
- **THEN** its socket file is `robot.sock` in the working directory, and a process in the same directory connects with that name

#### Scenario: Empty name

- **WHEN** `pipe_address()` is called with an empty name
- **THEN** it raises `ValueError`

### Requirement: A process can listen on a pipe, and others can connect to it

The package SHALL export the coroutine functions `start_pipe_server(client_connected_cb, name)` and `open_pipe_connection(name)`, after `asyncio.start_unix_server()` and `asyncio.open_unix_connection()`. The server SHALL be an `asyncio.AbstractServer` that calls `client_connected_cb` with a reader and a writer for each connection, and `open_pipe_connection()` SHALL return a reader and a writer. Both SHALL use named pipes on Windows and Unix domain sockets elsewhere.

#### Scenario: Messages in both directions

- **WHEN** a process connects to a pipe server, and both sides run a `JsonRpcPeer` over their reader and writer
- **THEN** a request and its response pass, and so does a message of 1 MiB in each direction

#### Scenario: Several connections

- **WHEN** two processes connect to the same pipe server at the same time
- **THEN** each gets a connection of its own, and the messages of one do not reach the other

#### Scenario: Nobody listens

- **WHEN** a process connects to a name for which there is no pipe and no socket file
- **THEN** `open_pipe_connection()` raises `FileNotFoundError`, and its message names the address

#### Scenario: An event loop without pipes on Windows

- **WHEN** `start_pipe_server()` or `open_pipe_connection()` runs on Windows on an event loop that is not a proactor event loop
- **THEN** it raises `RuntimeError`, and the message names the proactor event loop

### Requirement: A pipe server refuses a name that is in use

`start_pipe_server()` SHALL raise an `OSError` with `errno.EADDRINUSE` whose message names the address if a server already listens on the name, on every platform, and the server already there SHALL keep working. On platforms other than Windows, it SHALL replace a socket file on which nobody listens.

#### Scenario: A server listens on the name

- **WHEN** a pipe server is started on a name that another pipe server listens on
- **THEN** the start raises `OSError` with `errno.EADDRINUSE`, and the message names the address
- **AND** the first server still accepts new connections

#### Scenario: The socket file of a server that was killed

- **WHEN** on Linux or macOS a pipe server is started on the path of a socket file that a killed server left behind
- **THEN** the server starts and accepts connections

#### Scenario: A regular file at the path

- **WHEN** on Linux or macOS a pipe server is started on the path of a regular file
- **THEN** the start raises `OSError` whose message names the path, and the file is unchanged

### Requirement: Closing a pipe server stops it listening and leaves its connections open

After `close()` of a pipe server, a new connection to its name SHALL NOT reach the server, and the connections that the server had accepted SHALL stay open until their writers are closed. A new connection SHALL fail; on Windows, it waits while an accepted connection is open, because the pipe is busy then, and fails once those connections have ended. On platforms other than Windows, closing SHALL remove the socket file.

#### Scenario: An accepted connection after close

- **WHEN** a pipe server has accepted a connection and is closed
- **THEN** messages still pass over that connection in both directions

#### Scenario: A new connection after close

- **WHEN** a process connects to the name of a pipe server that was closed and has no open connections
- **THEN** the connection fails with `FileNotFoundError`

#### Scenario: The socket file after close

- **WHEN** a pipe server on Linux or macOS is closed, on every supported Python version
- **THEN** its socket file is gone

### Requirement: A process can be started with a connection over a pipe

The package SHALL export the coroutine function `create_pipe_subprocess(*argv, **kwargs)`. It SHALL listen on a new address, start the process with `--pipe=<address>` as its last argument, return it with a reader and a writer for the first connection to that address, and then stop listening and remove the address. Off Windows, the address SHALL lie in a new directory that only the current user can enter. Further arguments SHALL go to `asyncio.create_subprocess_exec()`.

#### Scenario: A process that connects with the connection function

- **WHEN** a process started this way connects to the address of its last argument with `open_pipe_connection()` and runs a `JsonRpcPeer`, and the caller sends a request over the returned reader and writer
- **THEN** the caller receives the response

#### Scenario: A process with plain blocking reads and writes

- **WHEN** a process started this way connects to the address with blocking I/O, without asyncio, and reads each request before it writes its response
- **THEN** the messages pass in both directions

#### Scenario: Only the first connection

- **WHEN** the process has connected, and another process connects to the same address
- **THEN** that connection never reaches the caller
- **AND** on Linux and macOS it fails, and the directory of the address is gone
- **AND** on Windows it waits while the first connection is open, because the pipe is busy, and fails with `FileNotFoundError` once that connection has ended

#### Scenario: A process that exits before it connects

- **WHEN** the process exits with exit code 3 before it connects
- **THEN** the call raises `ConnectionError` whose message names the exit code, and the address is gone

#### Scenario: Cancelled while it waits for the connection

- **WHEN** the call is cancelled before the process has connected
- **THEN** the process has ended, and the address is gone

#### Scenario: Command that cannot be started

- **WHEN** the command does not exist
- **THEN** the call raises `FileNotFoundError`, and the address is gone

#### Scenario: Further arguments

- **WHEN** the caller passes `stdin=asyncio.subprocess.DEVNULL` and `cwd`
- **THEN** the process runs in that directory, and reading its stdin gives the end of the input at once

## MODIFIED Requirements

### Requirement: On Windows a process started without a console opens no window

On Windows, `create_stdio_subprocess()` and `create_pipe_subprocess()` SHALL start the process without a window if the caller has no console, unless the caller passes `creationflags`. If the caller has a console, the process SHALL share it.

#### Scenario: Caller without a console

- **WHEN** a caller without a console starts a process
- **THEN** the process is started with the flag `CREATE_NO_WINDOW`

#### Scenario: Caller with a console

- **WHEN** a caller with a console starts a process
- **THEN** the process is started without that flag, so that it writes to that console and gets its Ctrl+C

#### Scenario: Caller passes creationflags

- **WHEN** a caller without a console passes `creationflags`
- **THEN** the process is started with exactly these flags
