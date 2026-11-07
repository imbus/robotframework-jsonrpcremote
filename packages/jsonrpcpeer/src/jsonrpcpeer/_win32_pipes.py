"""stdio on Windows: I/O completion ports for an overlapped pipe, a thread of its own for a synchronous one.

Only ``stdio.py`` imports this module, and only on Windows.
"""

import _winapi
import asyncio
import ctypes
import msvcrt
import os
import queue
import subprocess
import sys
import threading
from asyncio import windows_utils
from collections.abc import Sequence
from typing import Any

from .stdio import _WritePipeProtocol

assert sys.platform == "win32"

_FILE_MODE_INFORMATION = 16
_FILE_SYNCHRONOUS_IO_ALERT = 0x10
_FILE_SYNCHRONOUS_IO_NONALERT = 0x20
_PROCESS_HANDLE_INFORMATION = 51
_STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
_OBJ_INHERIT = 0x2
_HANDLE_FLAG_INHERIT = 0x1
_THREAD_TERMINATE = 0x0001

# The marks of asyncio's own transports, so that drain() behaves as there.
_HIGH_WATER = 64 * 1024
_LOW_WATER = 16 * 1024
_READ_SIZE = 64 * 1024
_CANCEL_INTERVAL = 0.05


class _IoStatusBlock(ctypes.Structure):
    _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_void_p)]


class _HandleEntry(ctypes.Structure):
    """One handle in the answer of NtQueryInformationProcess() to ProcessHandleInformation."""

    _fields_ = [
        ("HandleValue", ctypes.c_void_p),
        ("HandleCount", ctypes.c_size_t),
        ("PointerCount", ctypes.c_size_t),
        ("GrantedAccess", ctypes.c_ulong),
        ("ObjectTypeIndex", ctypes.c_ulong),
        ("HandleAttributes", ctypes.c_ulong),
        ("Reserved", ctypes.c_ulong),
    ]


_ntdll = ctypes.WinDLL("ntdll")
_ntdll.NtQueryInformationFile.restype = ctypes.c_long
_ntdll.NtQueryInformationFile.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_IoStatusBlock),
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.c_int,
]
_ntdll.NtQueryInformationProcess.restype = ctypes.c_long
_ntdll.NtQueryInformationProcess.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.POINTER(ctypes.c_ulong),
]

_kernelbase = ctypes.WinDLL("kernelbase")
_kernelbase.CompareObjectHandles.restype = ctypes.c_int
_kernelbase.CompareObjectHandles.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenThread.restype = ctypes.c_void_p
_kernel32.OpenThread.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
_kernel32.CancelSynchronousIo.restype = ctypes.c_int
_kernel32.CancelSynchronousIo.argtypes = [ctypes.c_void_p]
_kernel32.CloseHandle.restype = ctypes.c_int
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.GetConsoleCP.restype = ctypes.c_uint
_kernel32.GetConsoleCP.argtypes = []
_kernel32.SetHandleInformation.restype = ctypes.c_int
_kernel32.SetHandleInformation.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]


def is_overlapped(handle: int) -> bool:
    """Whether the handle was opened for overlapped I/O, which I/O completion ports need. Libuv asks the same."""
    status_block = _IoStatusBlock()
    mode = ctypes.c_ulong()
    status = _ntdll.NtQueryInformationFile(
        handle, ctypes.byref(status_block), ctypes.byref(mode), ctypes.sizeof(mode), _FILE_MODE_INFORMATION
    )
    if status != 0:
        return False
    return not mode.value & (_FILE_SYNCHRONOUS_IO_ALERT | _FILE_SYNCHRONOUS_IO_NONALERT)


def private_handle(fd: int) -> int:
    """A duplicate of the handle behind ``fd`` that child processes do not inherit; it is overlapped if that is."""
    process = _winapi.GetCurrentProcess()
    return _winapi.DuplicateHandle(process, msvcrt.get_osfhandle(fd), process, 0, False, _winapi.DUPLICATE_SAME_ACCESS)


def _inheritable_handles() -> list[int]:
    """The handles of this process that a child process inherits, if it inherits all."""
    size = 64 * 1024
    while True:
        snapshot = ctypes.create_string_buffer(size)
        needed = ctypes.c_ulong()
        status = _ntdll.NtQueryInformationProcess(
            _winapi.GetCurrentProcess(), _PROCESS_HANDLE_INFORMATION, snapshot, size, ctypes.byref(needed)
        )
        if status & 0xFFFFFFFF != _STATUS_INFO_LENGTH_MISMATCH:
            break
        size = max(2 * size, needed.value)
    if status != 0:
        return []
    # The snapshot starts with the number of handles and a reserved field.
    count = ctypes.c_size_t.from_buffer(snapshot).value
    entries = (_HandleEntry * count).from_buffer(snapshot, 2 * ctypes.sizeof(ctypes.c_size_t))
    return [entry.HandleValue for entry in entries if entry.HandleAttributes & _OBJ_INHERIT]


def keep_from_children(*handles: int) -> None:
    """Let no child process inherit another handle of this process to the objects of ``handles``.

    CPython's own launcher, the ``python.exe`` of a venv made with ``python -m venv`` and ``py.exe``, hands
    the standard handles to Python as inheritable duplicates, and the originals come along. A child process
    that inherits all handles, as one of ``os.system()`` does, would then keep the connection open.
    """
    for candidate in _inheritable_handles():
        if any(_kernelbase.CompareObjectHandles(candidate, handle) for handle in handles):
            _kernel32.SetHandleInformation(candidate, _HANDLE_FLAG_INHERIT, 0)


def check_loop() -> None:
    """Raise if stdin or stdout is an overlapped pipe and the running event loop cannot use it."""
    if isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
        return
    if is_overlapped(msvcrt.get_osfhandle(0)) or is_overlapped(msvcrt.get_osfhandle(1)):
        raise RuntimeError("stdio on Windows needs the proactor event loop for overlapped pipes")


class _ThreadReadTransport(asyncio.ReadTransport):
    """Reads a synchronous pipe in a thread of its own, because I/O completion ports cannot use it.

    It calls ReadFile() on the handle itself: the C runtime would add a lock per descriptor that close() has
    to wait for.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, handle: int, protocol: asyncio.Protocol) -> None:
        super().__init__({"pipe": handle})
        self._loop = loop
        self._protocol = protocol
        self._handle = handle
        self._closing = False
        self._reading = threading.Event()
        self._reading.set()
        self._thread = threading.Thread(target=self._read, name="jsonrpcpeer-stdin", daemon=True)
        protocol.connection_made(self)
        self._thread.start()

    def _read(self) -> None:
        try:
            while True:
                self._reading.wait()
                if self._closing:
                    return
                try:
                    data, _ = _winapi.ReadFile(self._handle, _READ_SIZE)
                except BrokenPipeError:
                    # The other end has closed the pipe.
                    data = b""
                self._loop.call_soon_threadsafe(self._received, data)
                if not data:
                    return
        except OSError as error:
            # Also how close() ends a read that blocks, through CancelSynchronousIo().
            self._loop.call_soon_threadsafe(self._lost, error)
        except RuntimeError:
            # The event loop has been closed, so nobody waits for the data any more.
            pass

    def _received(self, data: bytes) -> None:
        if self._closing:
            return
        if data:
            self._protocol.data_received(data)
        elif not self._protocol.eof_received():
            self.close()

    def _lost(self, error: OSError) -> None:
        if self._closing:
            return
        self._closing = True
        self._protocol.connection_lost(error)
        self._close_when_done()

    def _close_when_done(self) -> None:
        """Close the handle once the thread has ended, and until then cancel the read it blocks in."""
        if not self._thread.is_alive():
            _winapi.CloseHandle(self._handle)
            return
        thread = _kernel32.OpenThread(_THREAD_TERMINATE, False, self._thread.native_id)
        if thread:
            _kernel32.CancelSynchronousIo(thread)
            _kernel32.CloseHandle(thread)
        # The thread can be between two reads, where there is nothing to cancel, so try again.
        self._loop.call_later(_CANCEL_INTERVAL, self._close_when_done)

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        # A paused thread wakes up and ends.
        self._reading.set()
        self._loop.call_soon(self._protocol.connection_lost, None)
        self._close_when_done()

    def is_reading(self) -> bool:
        return self._reading.is_set() and not self._closing

    def pause_reading(self) -> None:
        self._reading.clear()

    def resume_reading(self) -> None:
        self._reading.set()


class _ThreadWriteTransport(asyncio.WriteTransport):
    """Writes a synchronous pipe in a thread of its own, so that a full pipe does not block the event loop.

    It calls WriteFile() on the handle itself: through the C runtime, a pipe that the other end has closed
    gives EINVAL instead of BrokenPipeError.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, handle: int, protocol: asyncio.BaseProtocol) -> None:
        super().__init__({"pipe": handle})
        self._loop = loop
        self._protocol = protocol
        self._handle = handle
        self._chunks: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()
        self._buffered = 0
        self._paused = False
        self._closing = False
        self._aborted = False
        self._lost = False
        self._thread = threading.Thread(target=self._write, name="jsonrpcpeer-stdout", daemon=True)
        protocol.connection_made(self)
        self._thread.start()

    def _write(self) -> None:
        error: OSError | None = None
        try:
            while (chunk := self._chunks.get()) is not None and not self._aborted:
                view = memoryview(chunk)
                while view:
                    written, _ = _winapi.WriteFile(self._handle, view)
                    view = view[written:]
                self._loop.call_soon_threadsafe(self._written, len(chunk))
        except OSError as exc:
            error = exc
        except RuntimeError:
            # The event loop has been closed, so nobody waits for the rest any more.
            pass
        finally:
            _winapi.CloseHandle(self._handle)
        try:
            self._loop.call_soon_threadsafe(self._connection_lost, error)
        except RuntimeError:
            pass

    def _written(self, size: int) -> None:
        self._buffered -= size
        if self._paused and self._buffered <= _LOW_WATER:
            self._paused = False
            self._protocol.resume_writing()

    def _connection_lost(self, error: OSError | None) -> None:
        if self._lost:
            return
        self._lost = True
        self._closing = True
        self._buffered = 0
        self._protocol.connection_lost(error)

    def write(self, data: bytes | bytearray | memoryview) -> None:
        if self._closing or not data:
            return
        self._chunks.put(bytes(data))
        self._buffered += len(data)
        if not self._paused and self._buffered > _HIGH_WATER:
            self._paused = True
            self._protocol.pause_writing()

    def get_write_buffer_size(self) -> int:
        return self._buffered

    def get_write_buffer_limits(self) -> tuple[int, int]:
        return _LOW_WATER, _HIGH_WATER

    def can_write_eof(self) -> bool:
        return True

    def write_eof(self) -> None:
        self.close()

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        """Write what is queued, then close the pipe."""
        if self._closing:
            return
        self._closing = True
        self._chunks.put(None)

    def abort(self) -> None:
        """Drop what is still queued, and close the pipe once a write that has begun has returned."""
        self._aborted = True
        if not self._closing:
            self._closing = True
            self._chunks.put(None)


class _ClosingReaderProtocol(asyncio.StreamReaderProtocol):
    """Closes its transport at the end of the input, because no writer closes it."""

    def eof_received(self) -> bool:
        super().eof_received()
        return False


async def connect(
    read_handle: int, write_handle: int, *, half_close: bool = False
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """The pair for two handles: I/O completion ports for an overlapped one, a thread for a synchronous one.

    The transports take over the handles. Closing the writer also closes the reader, as on a socket;
    with ``half_close``, the reader goes on until the end of the input, as with the pipes of a process.
    """
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    read_protocol = _ClosingReaderProtocol(reader) if half_close else asyncio.StreamReaderProtocol(reader)
    read_transport: asyncio.BaseTransport
    if is_overlapped(read_handle):
        read_transport, _ = await loop.connect_read_pipe(lambda: read_protocol, windows_utils.PipeHandle(read_handle))
    else:
        read_transport = _ThreadReadTransport(loop, read_handle, read_protocol)
    write_protocol = _WritePipeProtocol(None if half_close else read_transport)
    write_transport: asyncio.WriteTransport
    if is_overlapped(write_handle):
        write_transport, _ = await loop.connect_write_pipe(
            lambda: write_protocol, windows_utils.PipeHandle(write_handle)
        )
    else:
        write_transport = _ThreadWriteTransport(loop, write_handle, write_protocol)
    return reader, asyncio.StreamWriter(write_transport, write_protocol, reader, loop)


def has_console() -> bool:
    """Whether this process has a console, also one without a window, as after ``CREATE_NO_WINDOW``."""
    return bool(_kernel32.GetConsoleCP())


async def create_stdio_subprocess(
    argv: Sequence[str], kwargs: dict[str, Any]
) -> tuple[asyncio.subprocess.Process, asyncio.StreamReader, asyncio.StreamWriter]:
    """Start a process with overlapped pipes on its stdin and stdout, where asyncio would give it synchronous ones.

    The pipes are duplex, because the proactor's write transport also reads from its pipe, to notice that the
    other end has closed it.
    """
    if "creationflags" not in kwargs and not has_console():
        # Without a console to share, a console program would open a window of its own.
        kwargs = {**kwargs, "creationflags": subprocess.CREATE_NO_WINDOW}
    child_stdin, parent_stdin = windows_utils.pipe(overlapped=(True, True), duplex=True)
    parent_stdout, child_stdout = windows_utils.pipe(overlapped=(True, True), duplex=True)
    # The descriptors own the child's ends, and closing them closes these.
    stdin_fd = msvcrt.open_osfhandle(child_stdin, os.O_RDONLY)
    stdout_fd = msvcrt.open_osfhandle(child_stdout, 0)
    try:
        process = await asyncio.create_subprocess_exec(*argv, stdin=stdin_fd, stdout=stdout_fd, **kwargs)
    except BaseException:
        _winapi.CloseHandle(parent_stdin)
        _winapi.CloseHandle(parent_stdout)
        raise
    finally:
        os.close(stdin_fd)
        os.close(stdout_fd)
    # When the process ends, the write side notices it first; the reader still gets the rest of the output.
    reader, writer = await connect(parent_stdout, parent_stdin, half_close=True)
    return process, reader, writer
