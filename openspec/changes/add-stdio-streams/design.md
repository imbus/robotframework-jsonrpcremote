# Design

## Context

See proposal.md for the motivation. Today, `_stdio_streams()` in the server's `__main__.py` hands `sys.stdin.buffer` and `sys.stdout.buffer` to `loop.connect_read_pipe()` and `loop.connect_write_pipe()`, with `asyncio.streams.FlowControlMixin` as the write protocol.

- **File descriptors:** Robot Framework's `logger.console()` writes to `sys.__stdout__`, and child processes and C code use file descriptor 1 directly. Replacing `sys.stdout` alone would reach none of them.
- **`wait_closed()`:** `FlowControlMixin._get_close_waiter()` raises `NotImplementedError`, so `writer.wait_closed()` raises for this pair. `peer.py` and `tests/test_server_stdio.py` work around it.
- **Read side:** nothing closes the read transport if the writer closes first.
- **Closing `sys.stdout.buffer`:** closing the writer closes it, so a later `print()` raises `ValueError`.

This design was tried out as a prototype in a copy of the repository, together with `add-windows-stdio`, in one run per version. On Linux, with Python 3.12, 3.13, 3.14, 3.15 and 3.14t, the scenarios of the delta spec for `jsonrpc-peer` passed. With 3.12 and 3.14t, 309 unit tests passed, leaving out the in-process tests that the new ones replace, and all Robot suites passed, 88 of 88, with the new `atests/stdio_output.robot` and `atests/stdio_own_server.robot`. The checks of the server's stderr were not part of it. The results on Windows are in the design of `add-windows-stdio`.

## Goals / Non-Goals

**Goals:**

- A hand-written Python server gets a working connection over stdio with one call, and cannot corrupt it by printing or by starting a child process.
- The pair behaves like the pair of `asyncio.open_connection()`, so that code written for TCP also works here.

**Non-Goals:**

- Windows. There, the function raises the error that the server raises today. `add-windows-stdio` replaces it.
- A general transport interface (the rest of NET-5). The peer keeps taking a reader and a writer.
- Named pipes and Unix domain sockets (NET-1, NET-3). They will be the recommended way to connect a local server. Stdio stays the simplest one.
- A statement that the code is free of races under free-threading. The job shows that the tests pass with the GIL off, so there is no classifier for free-threading.

## Decisions

### 1. A function named after `asyncio.open_connection()`

```python
from jsonrpcpeer import JsonRpcPeer, open_stdio_connection

reader, writer = await open_stdio_connection()
peer = JsonRpcPeer(reader, writer)
```

The name follows `asyncio.open_connection()` and `asyncio.open_unix_connection()`, which also return such a pair, and leaves room for later transports. It lives in the new module `jsonrpcpeer/stdio.py` and is exported by the package. A transport class would add a concept that the peer does not need.

### 2. The move works on the file descriptors 0 and 1, and is not optional

```python
async def open_stdio_connection() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    _check_stdin()
    _check_stdout()
    _occupy_closed_stderr()
    read_file = os.fdopen(os.dup(0), "rb", 0)
    write_file = os.fdopen(os.dup(1), "wb", 0)
    _move_standard_streams()
    return await _connect(read_file, write_file)
```

- **The numbers 0 and 1, not `sys.stdin.fileno()`:** these two numbers are what child processes inherit and what C code writes to. A host may have replaced `sys.stdout` with an object without a file descriptor.
- **`os.dup()` for the private duplicates:** the new descriptors are not inheritable (PEP 446), so child processes do not keep the pipes open. That gives the requirement "A child process does not keep the connection open".
- **`os.dup2()` for the move:** `os.dup2(null, 0)` and `os.dup2(2, 1)` leave 0 and 1 inheritable, so child processes inherit the moved streams. `sys.stdin`, `sys.stdout` and `sys.__stdout__` wrap these numbers and follow without any change.
- **Non-blocking mode:** asyncio makes the pipes non-blocking, which applies to every duplicate of a descriptor. After the move, the private duplicates are the only ones in the process.
- **The move comes before the first `await`:** no task can write to the protocol channel between the check and the move. A refusal happens before the move, so stdin and stdout stay as they are.
- **No option to leave the streams:** this was Daniel's decision. Without the move, one `print()` can break a hand-written server later, under load, as the example server showed. The cost is that output on stdout cannot be sent to the client as protocol-free text, which was never possible.

Calling the function a second time is refused by the check of stdin, which then finds the null device.

### 3. `sys.stdout` becomes line-buffered

`sys.stdout` of a process with a pipe on stdout buffers blocks. After the move it writes to a person reading stderr, and a line that shows up only at exit, or never if the process is killed, is of little use. So `_move_standard_streams()` ends with this:

```python
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(line_buffering=True)
```

`reconfigure()` also flushes, after the move, so text buffered before the call goes to stderr too. The check is there because a host may have replaced `sys.stdout`. Replacing `sys.stdout` with `sys.stderr` instead would leave the buffered text behind in the old object.

### 4. A closed stderr gets the null device first

With file descriptor 2 closed, `os.dup(0)` returns 2, so the private read end takes the place of stderr, and `os.dup2(2, 1)` then points stdout at it. The prototype showed this as a connection that ended at once. So before the duplicates, `_occupy_closed_stderr()` checks 2 with `os.fstat()`, and if it is closed, puts the null device there. This also keeps a later write to file descriptor 2 away from whatever file gets that number. A closed stdin or stdout is refused before anything is duplicated, so they cannot take that place.

### 5. A write protocol that makes the pair close like a socket

```python
class _WritePipeProtocol(asyncio.streams.FlowControlMixin):
    """The write side of a pair: wait_closed() works, and closing it closes the read side, as on a socket."""

    def __init__(self, read_transport: asyncio.BaseTransport, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(loop=loop)
        self._read_transport = read_transport
        self._closed = loop.create_future()

    def connection_lost(self, exc: Exception | None) -> None:
        super().connection_lost(exc)
        self._read_transport.close()
        if self._closed.done():
            return
        if exc is None:
            self._closed.set_result(None)
        else:
            self._closed.set_exception(exc)
            self._closed.exception()  # Retrieved, so that asyncio does not report it; wait_closed() still raises it.

    def _get_close_waiter(self, stream: asyncio.StreamWriter) -> "asyncio.Future[None]":
        return self._closed
```

- **A public function should return a pair whose `wait_closed()` works**, as `asyncio.open_connection()` does. It is the idiom that every asyncio example uses.
- **Why not `asyncio.StreamReaderProtocol` for the write side:** it would need a stream reader that nobody reads.
- **Private API:** `_get_close_waiter()` is what `StreamWriter.wait_closed()` calls, and `FlowControlMixin` is undocumented, though the existing code and much other code use it. The prototype passed on 3.12 to 3.15, and CI runs these versions.
- **`writer.wait_closed()` now really waits** until the pipe has taken the buffered data, so it waits as long as the other end does not read. This does not hold up the server's stop, because `peer.run()` returns as soon as the peer's completion is set, before the close. Checked with SIGTERM to a server with 19.9 MB of a response in its write buffer and a client that did not read: exit code 0 after 0.1 s, the same as without this protocol.
- **The comment in `peer.py`** that names the stdio pipe as an example of a writer that raises from `wait_closed()` goes away; the code stays for other writers. `test_stdio_streams_connect_a_pipe` and its comment go away too (decision 7).

The end of the input does not close the writer, because the peer or the application decides when it is done, as with a half-closed socket.

### 6. The server and the example server use the function

- **Server:** `run_stdio_server()` calls `open_stdio_connection()`. `_stdio_streams()` is removed, and `_check_stdio_stdin()` moves to `stdio.py` as `_check_stdin()`, with its messages unchanged, so that the requirement "stdio mode needs a stdin it can watch" and its tests stay as they are. The check of stdout is new.
- **Windows until `add-windows-stdio`:** `open_stdio_connection()` raises `RuntimeError("stdio mode is not supported on Windows; use --tcp instead.")`, so the server, its tests and `atests/stdio_windows.robot` stay as they are there.
- **Example server:** `run()` gets the option `--stdio` and then runs `handle_client(*await open_stdio_connection())`. Its `print()` calls stay, because they are what the move is for. `addr` falls back to the word `stdio`, because a pipe has no `peername`.

### 7. Tests run the function in a process of its own

The function changes the file descriptors of its process, which would break pytest's capture and every later test. So:

- **`tests/test_stdio_connection.py`** runs a short script per scenario in a child process with its stdin, stdout and stderr as pipes, and checks what arrives on each. The checks of stdin and stdout are in the script, too. It has `skipif(win32)` until `add-windows-stdio`.
- **`tests/test_server_stdio.py`:** the tests with a fake pair patch `server_main.open_stdio_connection`. `test_stdio_streams_reject_a_stdin_that_cannot_be_watched` and `test_stdio_streams_connect_a_pipe` move to the new file, because they monkeypatch `sys.stdin`, which the function no longer reads. New tests run the real server with `atests/StdioOutputLib.py` and captured stderr, and check the text there, which a Robot test cannot see.
- **`atests/stdio_output.robot`** with `atests/StdioOutputLib.py` calls keywords that reach past Robot Framework's capture, each followed by a call that shows the connection still works. Its library has `rpc_scope=TEST`, so that a broken connection fails one test only, and so that the test with the exiting server can stand on its own.
- **`atests/stdio_own_server.robot`** runs the example server over stdio with a message of 20,000 characters, which is what makes its `print()` calls overflow the 8 KiB buffer of `sys.stdout`. A larger message would only fill the CI log, because the example prints its arguments.

### 8. CI: the matrix gets 3.14t, and a step checks the GIL

```yaml
python: ["3.12", "3.13", "3.14", "3.14t", "3.15"]
```

```yaml
# Importing a C extension without support for free-threading turns the GIL on, and the job would test nothing new.
- name: Check that the GIL is off
  if: endsWith(matrix.python, 't')
  run: uv run --all-packages python -c "import sys, hypothesis, pytest, robot, robotcode.cli, JsonRpcRemote, robot_jsonrpcremote_server; sys.exit(sys._is_gil_enabled())"
```

- **In the matrix, not in a job of its own:** one word gives all the steps on all three operating systems. `setup-uv` sets `UV_PYTHON`, and uv accepts `3.14t`.
- **Checked by hand:** `uv sync --all-packages` with `UV_PYTHON=3.14t` installs all dev dependencies from wheels on Linux, and the GIL stays off after importing the packages in the step. macOS is checked only by the first CI run.
- **Why not `PYTHON_GIL=0`:** it would keep the GIL off with such a C extension, which is then unsupported, and hide the problem. The step makes it visible.
- **Only 3.14t:** one free-threaded build is enough to notice a change in behavior; the VM also passed on 3.15t.
- **`print` from several threads mixes lines on a free-threaded build,** on all pipes. The protocol is not affected, because only the event loop writes to the private duplicate. No test depends on it.

## Risks / Trade-offs

- [The output of child processes now appears on the console of `robot`, because the server inherits its stderr] → That is the purpose. Whoever wants less starts the child with captured output.
- [A process whose parent gives it a stderr pipe and does not read it can block once the pipe is full] → That holds for every program, and more now goes there. `JsonRpcRemote` lets the server inherit stderr. The page says that output goes to stderr.
- [A regression in `atests/stdio_output.robot` shows as a call that hangs, because no keyword timeout exists] → The job timeout of 20 minutes ends it. The checks against the code without the change run under `timeout`, as tasks.md says.
- [`wait_closed()` depends on private API of asyncio] → CI runs every supported version. If it breaks, `writer.wait_closed()` raises again, which the peer tolerates.
- [The job with 3.14t can turn red because a new version of a dev dependency turns the GIL on or has no wheel] → The dependencies are locked in `uv.lock`, so this shows when the lock file is updated, not by itself.

## Migration Plan

None. `_stdio_streams()` is private, and the project is in pre-alpha.
