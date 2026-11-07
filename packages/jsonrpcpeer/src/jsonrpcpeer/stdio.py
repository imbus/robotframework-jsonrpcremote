import asyncio
import io
import os
import selectors
import stat
import sys
from typing import Any, BinaryIO

_STDIN_NEEDED = "stdio mode needs a stdin that can be watched for input, such as a pipe"


def _check_stdin() -> None:
    """Raise unless stdin is open and the event loop can watch it for input.

    An unwatchable stdin such as /dev/null would otherwise never deliver data or EOF.
    """
    # A process that started without a stdin has sys.__stdin__ set to None, and a file opened since
    # then, such as the selector of the event loop, can have taken file descriptor 0.
    if sys.__stdin__ is None:
        raise RuntimeError(f"{_STDIN_NEEDED}, but stdin is closed")
    try:
        mode = os.fstat(0).st_mode
    except OSError:
        raise RuntimeError(f"{_STDIN_NEEDED}, but stdin is closed") from None

    # The type rule holds on every platform, whatever its selector would accept. On Windows, only a
    # pipe can be read without blocking the event loop, and os.isatty() is true for the null device.
    if sys.platform == "win32":
        accepted = stat.S_ISFIFO(mode)
    else:
        accepted = stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode) or os.isatty(0)
    if not accepted:
        if stat.S_ISREG(mode):
            found = "a regular file"
        elif stat.S_ISCHR(mode):
            found = f"a character device such as {os.devnull}"
        else:
            found = "neither a pipe, a socket nor a terminal"
        raise RuntimeError(f"{_STDIN_NEEDED}, but stdin is {found}")

    # Not every selector can watch every kind of stdin, for example a terminal on macOS. On Windows,
    # no selector watches a pipe, and the event loop reads it through I/O completion ports or a thread.
    if sys.platform != "win32":
        with selectors.DefaultSelector() as probe:
            try:
                probe.register(0, selectors.EVENT_READ)
            except (OSError, ValueError) as error:
                raise RuntimeError(f"{_STDIN_NEEDED}, but the event loop cannot watch it: {error}") from error


def _check_stdout() -> None:
    closed = RuntimeError("stdio mode needs an open stdout, but stdout is closed")
    # As for stdin, file descriptor 1 can belong to another file if the process started without it.
    if sys.__stdout__ is None:
        raise closed
    try:
        os.fstat(1)
    except OSError:
        raise closed from None


def _occupy_closed_stderr() -> None:
    """Put the null device on a closed stderr.

    Otherwise the next file of the process gets its number: a private duplicate of the connection,
    which the move would then turn into stdout, or a file that output for stderr would reach.
    """
    try:
        os.fstat(2)
    except OSError:
        null = os.open(os.devnull, os.O_WRONLY)
        if null != 2:
            os.dup2(null, 2)
            os.close(null)


def _move_standard_streams() -> None:
    """Point stdin at the null device and stdout at stderr, also for child processes and C code.

    On Windows, the C runtime of a console program such as python.exe also sets the standard
    handles, which native code and child processes use, when a descriptor from 0 to 2 changes.
    """
    null = os.open(os.devnull, os.O_RDWR)
    os.dup2(null, 0)
    # A process that started without a stderr has sys.__stderr__ set to None, and a file opened
    # since then, such as the selector of the event loop, can have taken file descriptor 2.
    os.dup2(2 if sys.__stderr__ is not None else null, 1)
    os.close(null)
    # A person reads stderr, so a line should show up when it is printed. Reconfiguring also
    # flushes, so text buffered before the move goes to stderr too.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)


class _WritePipeProtocol(asyncio.streams.FlowControlMixin):
    """The write side of a pair: wait_closed() works, and closing it closes ``read_transport``, as on a socket."""

    def __init__(self, read_transport: asyncio.BaseTransport | None) -> None:
        super().__init__()
        self._read_transport = read_transport
        self._closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def connection_lost(self, exc: Exception | None) -> None:
        super().connection_lost(exc)
        if self._read_transport is not None:
            self._read_transport.close()
        if self._closed.done():
            return
        if exc is None:
            self._closed.set_result(None)
        else:
            self._closed.set_exception(exc)
            # Retrieved, so that asyncio does not report it; wait_closed() still raises it.
            self._closed.exception()

    def _get_close_waiter(self, stream: asyncio.StreamWriter) -> "asyncio.Future[None]":
        return self._closed


async def _connect(read_file: BinaryIO, write_file: BinaryIO) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """The reader and writer for two pipes. The transports take over the files."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    read_transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), read_file)
    write_transport, write_protocol = await loop.connect_write_pipe(
        lambda: _WritePipeProtocol(read_transport), write_file
    )
    return reader, asyncio.StreamWriter(write_transport, write_protocol, reader, loop)


async def open_stdio_connection() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Return a reader and a writer for the stdin and stdout of this process, for a ``JsonRpcPeer``.

    The connection uses private duplicates of stdin and stdout, which child processes do not
    inherit, and moves the standard streams out of its way: afterwards, stdin reads from the null
    device and stdout writes to stderr, also for child processes and C code. So only what is
    written to the returned writer reaches the original stdout.

    On Windows, an overlapped pipe goes through the I/O completion ports of the proactor event
    loop, and a synchronous pipe gets a thread of its own for its direction.

    Raises ``RuntimeError`` and leaves the standard streams as they are if stdin cannot be watched
    for input, as a pipe or a socket can, if stdin or stdout is closed, or on Windows if stdin is
    no pipe, or if an overlapped pipe meets an event loop that is not a proactor.
    """
    _check_stdin()
    _check_stdout()
    _occupy_closed_stderr()
    # Before the first await, so that no task can write to the connection between check and move.
    if sys.platform == "win32":
        from . import _win32_pipes

        _win32_pipes.check_loop()
        read_handle = _win32_pipes.private_handle(0)
        write_handle = _win32_pipes.private_handle(1)
        _move_standard_streams()
        _win32_pipes.keep_from_children(read_handle, write_handle)
        connecting = _win32_pipes.connect(read_handle, write_handle)
    else:
        read_file = os.fdopen(os.dup(0), "rb", 0)
        write_file = os.fdopen(os.dup(1), "wb", 0)
        _move_standard_streams()
        connecting = _connect(read_file, write_file)
    return await connecting


async def create_stdio_subprocess(
    *argv: str, **kwargs: Any
) -> tuple[asyncio.subprocess.Process, asyncio.StreamReader, asyncio.StreamWriter]:
    """Start a process and return it with a reader for its stdout and a writer for its stdin, for a ``JsonRpcPeer``.

    Further arguments go to ``asyncio.create_subprocess_exec()``. On Windows, stdin and stdout are
    overlapped pipes, which the process can use through I/O completion ports, and on other
    platforms ordinary pipes. Closing the writer ends the input of the process; the reader ends
    when the process has closed its stdout.

    If the caller on Windows has no console and passes no ``creationflags``, the process is started
    with ``CREATE_NO_WINDOW``, so that a console program does not open a window of its own.
    """
    if sys.platform == "win32":
        from . import _win32_pipes

        starting = _win32_pipes.create_stdio_subprocess(argv, kwargs)
    else:
        starting = _create_subprocess_with_pipes(argv, kwargs)
    return await starting


async def _create_subprocess_with_pipes(
    argv: tuple[str, ...], kwargs: dict[str, Any]
) -> tuple[asyncio.subprocess.Process, asyncio.StreamReader, asyncio.StreamWriter]:
    process = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, **kwargs
    )
    assert process.stdout is not None
    assert process.stdin is not None
    return process, process.stdout, process.stdin
