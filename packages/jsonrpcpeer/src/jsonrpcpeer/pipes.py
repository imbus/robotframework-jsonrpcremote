r"""Pipes: named pipes on Windows, Unix domain sockets elsewhere.

Every function resolves the name of a pipe with ``pipe_address()``: on Windows, a bare name means
``\\.\pipe\<name>``; elsewhere, a name is the path of a socket file.
"""

import asyncio
import contextlib
import errno
import os
import secrets
import shutil
import sys
import tempfile
from collections.abc import Awaitable, Callable
from typing import Any

_ClientConnectedCallback = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None] | None]

# Every named pipe lives here. A name without it would reach CreateFile() as the name of a file.
_WINDOWS_PIPES = "\\\\.\\pipe\\"

# How long a cancelled create_pipe_subprocess() waits for the process that it has killed.
_KILL_TIMEOUT = 10.0


def pipe_address(name: str) -> str:
    r"""The address of the pipe ``name``: a named pipe on Windows, the path of a Unix domain socket elsewhere.

    On Windows, a name that starts with ``\\`` or ``//`` is used as it is, and any other name gets
    ``\\.\pipe\`` in front. Elsewhere, the name is used as it is, so a relative path is relative to
    the working directory. Raises ``ValueError`` for an empty name.
    """
    if not name:
        raise ValueError("a pipe needs a name")
    if sys.platform == "win32" and not name.startswith(("\\\\", "//")):
        return _WINDOWS_PIPES + name
    return name


def _naming(error: OSError, address: str) -> OSError:
    """``error`` with the address in its message, as for a file; the errors of asyncio and of sockets lack it."""
    if error.filename is not None or repr(address) in str(error):
        return error
    if error.errno is None:
        # Such as "AF_UNIX path too long", which has no error number.
        return type(error)(f"{error}: {address!r}")
    return type(error)(error.errno, error.strerror, address)


def _in_use(address: str) -> OSError:
    return OSError(errno.EADDRINUSE, "Address already in use", address)


async def open_pipe_connection(name: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the pipe ``name`` and return a reader and a writer, as ``asyncio.open_unix_connection()`` does.

    On Windows, it needs the proactor event loop. Errors name the address, also ``FileNotFoundError``
    when nobody listens there.
    """
    address = pipe_address(name)
    try:
        if sys.platform == "win32":
            from . import _win32_pipes

            connecting = _win32_pipes.open_pipe_connection(address)
        else:
            connecting = asyncio.open_unix_connection(address)
        return await connecting
    except OSError as error:
        raise _naming(error, address) from None


async def start_pipe_server(client_connected_cb: _ClientConnectedCallback, name: str) -> asyncio.AbstractServer:
    """Listen on the pipe ``name`` and call ``client_connected_cb`` with a reader and a writer for each connection.

    As ``asyncio.start_unix_server()`` does, but on every platform, and without taking a name from a
    server that listens there: then it raises ``OSError`` with ``errno.EADDRINUSE``. Elsewhere than on
    Windows, it replaces a socket file on which nobody listens, and closing the server removes its
    socket file, if it is still the file that the server made.

    On Windows, it needs the proactor event loop, and ``wait_closed()`` of the server does not wait for
    the connections that it has accepted. A new connection after ``close()`` waits there while an
    accepted connection is open, because the pipe is busy. Errors name the address.
    """
    address = pipe_address(name)
    try:
        if sys.platform == "win32":
            from . import _win32_pipes

            starting = _win32_pipes.start_pipe_server(client_connected_cb, address)
        else:
            starting = _start_socket_file_server(client_connected_cb, address)
        return await starting
    except OSError as error:
        raise _naming(error, address) from None


if sys.platform != "win32":

    async def _start_socket_file_server(
        client_connected_cb: _ClientConnectedCallback, path: str
    ) -> asyncio.AbstractServer:
        await _refuse_a_listening_socket(path)
        server = await asyncio.start_unix_server(client_connected_cb, path)
        return _SocketFileServer(server, path)

    async def _refuse_a_listening_socket(path: str) -> None:
        """Raise if a server listens on the socket file at ``path``: asyncio would remove the file and take its path."""
        try:
            _, writer = await asyncio.open_unix_connection(path)
        except OSError:
            # No file, or one on which nobody listens: asyncio replaces a socket file, and refuses any other.
            return
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()
        raise _in_use(path)


class _SocketFileServer(asyncio.AbstractServer):
    """The server of asyncio on a socket file, which it removes when it is closed: Python 3.12 leaves it behind."""

    def __init__(self, server: asyncio.Server, path: str) -> None:
        self._server = server
        # Absolute, in case the working directory changes while the server runs.
        self._path = os.path.abspath(path)
        self._inode: int | None = os.stat(path).st_ino

    def _remove_socket_file(self) -> None:
        inode, self._inode = self._inode, None
        if inode is None:
            return
        # Only the file that this server made: another server can have taken the path since.
        with contextlib.suppress(OSError):
            if os.stat(self._path).st_ino == inode:
                os.unlink(self._path)

    def close(self) -> None:
        self._server.close()
        self._remove_socket_file()

    def get_loop(self) -> asyncio.AbstractEventLoop:
        return self._server.get_loop()

    def is_serving(self) -> bool:
        return self._server.is_serving()

    async def start_serving(self) -> None:
        await self._server.start_serving()

    async def serve_forever(self) -> None:
        try:
            await self._server.serve_forever()
        finally:
            self._remove_socket_file()

    async def wait_closed(self) -> None:
        await self._server.wait_closed()


async def create_pipe_subprocess(
    *argv: str, **kwargs: Any
) -> tuple[asyncio.subprocess.Process, asyncio.StreamReader, asyncio.StreamWriter]:
    """Start a process with a connection over a pipe of its own, and return it with a reader and a writer.

    It listens on a new address and starts the process with ``--pipe=<address>`` as its last
    argument, as ``vscode-languageclient`` starts a language server. It returns once the process has
    connected, and then stops listening and removes the address, so that no other connection reaches
    the caller: on Windows, another connection waits while the first one is open, because the pipe is
    busy. Elsewhere than on Windows, the address is a socket file in a new directory that only the
    current user can enter.

    Further arguments go to ``asyncio.create_subprocess_exec()``, so the caller chooses stdin, stdout
    and stderr. If the caller on Windows has no console and passes no ``creationflags``, the process is
    started with ``CREATE_NO_WINDOW``, as by ``create_stdio_subprocess()``.

    Raises ``ConnectionError`` if the process exits before it connects. If the call is cancelled
    before the process has connected, it kills the process.
    """
    directory: str | None = None
    if sys.platform == "win32":
        from . import _win32_pipes

        kwargs = _win32_pipes.without_window(kwargs)
        # As many random bits as vscode-languageclient uses.
        address = f"{_WINDOWS_PIPES}jsonrpcpeer-{secrets.token_hex(16)}"
    else:
        # The directory has the mode 0700, so only the current user can reach the socket file.
        directory = tempfile.mkdtemp(prefix="jsonrpcpeer-")
        address = os.path.join(directory, "pipe")
    connected: asyncio.Future[tuple[asyncio.StreamReader, asyncio.StreamWriter]]
    connected = asyncio.get_running_loop().create_future()
    server: asyncio.AbstractServer | None = None

    def stop_listening() -> None:
        if server is not None:
            server.close()
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)

    def on_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if connected.done():
            # Accepted before the listener was closed, or after the call has ended without a connection.
            writer.close()
            return
        # Here, and not after the wait: on Windows, closing breaks a connection whose callback has not run yet.
        stop_listening()
        connected.set_result((reader, writer))

    try:
        server = await start_pipe_server(on_connection, address)
        process = await asyncio.create_subprocess_exec(*argv, f"--pipe={address}", **kwargs)
    except BaseException:
        stop_listening()
        raise

    exited = asyncio.ensure_future(process.wait())
    try:
        await asyncio.wait((connected, exited), return_when=asyncio.FIRST_COMPLETED)
    except BaseException:
        # Cancelled: the caller never gets the process, nor a connection that came at the same time.
        if connected.done():
            connected.result()[1].close()
        connected.cancel()
        stop_listening()
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(asyncio.shield(exited), _KILL_TIMEOUT)
        raise
    finally:
        if not exited.done():
            exited.cancel()
    if not connected.done():
        connected.cancel()
        stop_listening()
        raise ConnectionError(f"the process exited with code {process.returncode} before it connected to {address!r}")
    reader, writer = connected.result()
    return process, reader, writer
