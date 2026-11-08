"""Pipes: named pipes on Windows, Unix domain sockets elsewhere.

Every test changes into a directory of its own and uses a name of its own there. Elsewhere than on
Windows, a socket file is then short enough: its path can have at most 103 bytes on macOS, and
``tmp_path`` can be longer. On Windows, all named pipes share one namespace, so a name has a random part.
"""

import asyncio
import errno
import json
import os
import secrets
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from jsonrpcpeer import JsonRpcPeer, create_pipe_subprocess, open_pipe_connection, pipe_address, start_pipe_server

_WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="this behavior exists only on Windows")
_NOT_ON_WINDOWS = pytest.mark.skipif(sys.platform == "win32", reason="socket files exist only off Windows")

_MINIMAL_SERVER = Path(__file__).resolve().parent / "minimal_pipe_server.py"
_MIB = 1024 * 1024
# A hard limit for every wait, so that a connection that never comes fails the test instead of hanging it.
_TIMEOUT = 30


@pytest.fixture(autouse=True)
def _in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def name() -> str:
    """A name of its own for the test."""
    return f"jsonrpcpeer-test-{secrets.token_hex(8)}"


async def _echo(params: Any) -> Any:
    return params


class _EchoServer:
    """The peers on the connections of a pipe server, which answer ``echo`` with its params."""

    def __init__(self) -> None:
        self.server: asyncio.AbstractServer | None = None
        self.connections: list[asyncio.Task[Any]] = []
        self._accepted: asyncio.Queue[None] = asyncio.Queue()

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.connections.append(task)
        self._accepted.put_nowait(None)
        peer = JsonRpcPeer(reader, writer)
        peer.register_request_handler("echo", _echo)
        await peer.run()

    async def accepted(self) -> None:
        """Wait until the server has accepted the next connection."""
        await asyncio.wait_for(self._accepted.get(), _TIMEOUT)

    def close(self) -> None:
        assert self.server is not None
        self.server.close()


@asynccontextmanager
async def _echo_server(name: str) -> AsyncIterator[_EchoServer]:
    """A pipe server whose peers answer ``echo``; at the end, it waits until its connections have ended."""
    echo = _EchoServer()
    echo.server = await start_pipe_server(echo.serve, name)
    try:
        yield echo
    finally:
        echo.close()
        # The clients have closed their ends by now. On Windows, wait_closed() would not wait for the peers.
        await asyncio.wait_for(asyncio.gather(*echo.connections, return_exceptions=True), _TIMEOUT)


@asynccontextmanager
async def _peer(name: str) -> AsyncIterator[JsonRpcPeer]:
    """A started peer on a new connection to the pipe ``name``."""
    peer = JsonRpcPeer(*await asyncio.wait_for(open_pipe_connection(name), _TIMEOUT))
    peer.start()
    try:
        yield peer
    finally:
        await peer.stop()


async def _send(peer: JsonRpcPeer, params: Any) -> Any:
    return await asyncio.wait_for(peer.send_request("echo", params), _TIMEOUT)


async def _assert_gone(address: str) -> None:
    """Assert that nobody can connect to ``address`` any more, and that its directory is gone off Windows."""
    with pytest.raises(FileNotFoundError):
        await asyncio.wait_for(open_pipe_connection(address), _TIMEOUT)
    if sys.platform != "win32":
        assert not os.path.exists(os.path.dirname(address))


async def _end(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.kill()
    await asyncio.wait_for(process.wait(), _TIMEOUT)


# pipe_address()


@pytest.mark.parametrize(
    ("name", "address"),
    [
        pytest.param("robot", r"\\.\pipe\robot", id="bare_name"),
        pytest.param(r"\\.\pipe\robot", r"\\.\pipe\robot", id="full_name"),
        pytest.param("//./pipe/robot", "//./pipe/robot", id="full_name_with_slashes"),
    ],
)
def test_on_windows_a_bare_name_means_a_named_pipe(monkeypatch: pytest.MonkeyPatch, name: str, address: str) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    assert pipe_address(name) == address


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_an_empty_name_is_refused(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    monkeypatch.setattr(sys, "platform", platform)

    with pytest.raises(ValueError, match="name"):
        pipe_address("")


@_NOT_ON_WINDOWS
async def test_a_name_is_the_path_of_a_socket_file_relative_to_the_working_directory(tmp_path: Path) -> None:
    async with _echo_server("robot.sock"):
        assert (tmp_path / "robot.sock").is_socket()
        async with _peer("robot.sock") as peer:
            result = await _send(peer, {"text": "relative"})

    assert result == {"text": "relative"}


@_WINDOWS_ONLY
async def test_on_windows_a_full_name_is_used_as_written(name: str) -> None:
    async with _echo_server(rf"\\.\pipe\{name}") as echo:
        async with _peer(rf"\\.\pipe\{name}") as backslashes, _peer(f"//./pipe/{name}") as slashes:
            results = [await _send(backslashes, {"via": "backslashes"}), await _send(slashes, {"via": "slashes"})]

    assert results == [{"via": "backslashes"}, {"via": "slashes"}]
    assert len(echo.connections) == 2


@_WINDOWS_ONLY
async def test_on_windows_a_bare_name_never_opens_a_file(name: str) -> None:
    Path(name).write_text("not a pipe")

    with pytest.raises(FileNotFoundError):
        await asyncio.wait_for(open_pipe_connection(name), _TIMEOUT)

    # A file that a connection had opened could not be removed now.
    Path(name).unlink()


# open_pipe_connection() and start_pipe_server()


async def test_a_request_and_its_response_pass_also_with_a_message_of_one_mib(name: str) -> None:
    text = "x" * _MIB
    async with _echo_server(name), _peer(name) as peer:
        small = await _send(peer, {"text": "Grüße"})
        large = await _send(peer, {"text": text})

    assert small == {"text": "Grüße"}
    assert large == {"text": text}


async def test_each_connection_to_a_server_is_a_connection_of_its_own(name: str) -> None:
    async with _echo_server(name) as echo, _peer(name) as first, _peer(name) as second:
        # At the same time, and with the same request IDs: answers that crossed over would show.
        answers = await asyncio.gather(*(_send(peer, {"from": label}) for label, peer in [("1", first), ("2", second)]))

    assert answers == [{"from": "1"}, {"from": "2"}]
    assert len(echo.connections) == 2


async def test_connecting_where_nobody_listens_raises_file_not_found_error_that_names_the_address(name: str) -> None:
    with pytest.raises(FileNotFoundError) as caught:
        await asyncio.wait_for(open_pipe_connection(name), _TIMEOUT)

    assert caught.value.filename == pipe_address(name)
    assert name in str(caught.value)


@_WINDOWS_ONLY
def test_on_windows_pipes_on_an_event_loop_that_is_no_proactor_are_refused(name: str) -> None:
    async def attempt() -> list[str]:
        messages = []
        with pytest.raises(RuntimeError) as listening:
            await start_pipe_server(_EchoServer().serve, name)
        messages.append(str(listening.value))
        with pytest.raises(RuntimeError) as connecting:
            await open_pipe_connection(name)
        messages.append(str(connecting.value))
        return messages

    messages = asyncio.run(attempt(), loop_factory=asyncio.SelectorEventLoop)

    assert all("proactor event loop" in message for message in messages), messages


# A name in use


async def test_a_name_in_use_is_refused_and_the_server_there_keeps_working(name: str) -> None:
    async with _echo_server(name):
        # The message names the address.
        with pytest.raises(OSError, match=name) as caught:
            await start_pipe_server(_EchoServer().serve, name)
        async with _peer(name) as peer:
            result = await _send(peer, {"still": "there"})

    assert caught.value.errno == errno.EADDRINUSE
    assert result == {"still": "there"}


@_NOT_ON_WINDOWS
async def test_the_socket_file_of_a_killed_server_is_replaced(tmp_path: Path, name: str) -> None:
    # A socket that was bound and closed leaves its file behind, as a server that was killed does. The family
    # exists only off Windows, so it is named here, for the type check on Windows.
    left_over = socket.socket(getattr(socket, "AF_UNIX"))
    left_over.bind(name)
    left_over.close()
    assert (tmp_path / name).is_socket()

    async with _echo_server(name), _peer(name) as peer:
        result = await _send(peer, {"after": "a killed server"})

    assert result == {"after": "a killed server"}


@_NOT_ON_WINDOWS
async def test_a_regular_file_at_the_path_is_refused_and_stays_as_it_is(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("a regular file")

    # The message names the path.
    with pytest.raises(OSError, match=name):
        await start_pipe_server(_EchoServer().serve, name)

    assert (tmp_path / name).read_text() == "a regular file"


# Closing a pipe server


async def test_an_accepted_connection_stays_open_after_the_server_has_closed(name: str) -> None:
    async with _echo_server(name) as echo, _peer(name) as peer:
        # Accepted first: on Windows, closing breaks a connection whose callback has not run yet.
        await echo.accepted()
        echo.close()
        result = await _send(peer, {"after": "close"})

    assert result == {"after": "close"}


async def test_a_new_connection_after_close_fails_with_file_not_found_error(name: str) -> None:
    async with _echo_server(name) as echo:
        echo.close()

        with pytest.raises(FileNotFoundError):
            await asyncio.wait_for(open_pipe_connection(name), _TIMEOUT)


@_NOT_ON_WINDOWS
async def test_closing_the_server_removes_its_socket_file(tmp_path: Path, name: str) -> None:
    async with _echo_server(name) as echo:
        assert (tmp_path / name).is_socket()

        echo.close()

        assert not (tmp_path / name).exists()


# create_pipe_subprocess()


@dataclass
class _Start:
    argv: tuple[str, ...]
    process: asyncio.subprocess.Process | None = None

    @property
    def address(self) -> str:
        return self.argv[-1].removeprefix("--pipe=")


@pytest.fixture
def starts(monkeypatch: pytest.MonkeyPatch) -> list[_Start]:
    """Every start of a process, recorded on its way to asyncio."""
    starts: list[_Start] = []
    start_process = asyncio.create_subprocess_exec

    async def record(*argv: str, **kwargs: Any) -> asyncio.subprocess.Process:
        start = _Start(argv)
        starts.append(start)
        start.process = await start_process(*argv, **kwargs)
        return start.process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", record)
    return starts


_ECHO_PEER = """
import asyncio, sys
from jsonrpcpeer import JsonRpcPeer, open_pipe_connection

async def echo(params):
    return params

async def main():
    peer = JsonRpcPeer(*await open_pipe_connection(sys.argv[-1].removeprefix("--pipe=")))
    peer.register_request_handler("echo", echo)
    await peer.run()

asyncio.run(main())
"""


async def test_a_process_that_connects_with_the_connection_function_answers_a_request(starts: list[_Start]) -> None:
    process, reader, writer = await asyncio.wait_for(create_pipe_subprocess(sys.executable, "-c", _ECHO_PEER), _TIMEOUT)
    try:
        peer = JsonRpcPeer(reader, writer)
        peer.start()
        result = await _send(peer, {"text": "Grüße"})
        # Closing our end ends the connection, and the peer of the process ends.
        await peer.stop()
        code = await asyncio.wait_for(process.wait(), _TIMEOUT)
    finally:
        await _end(process)

    assert result == {"text": "Grüße"}
    assert code == 0
    assert starts[0].argv[-1].startswith("--pipe=")


async def test_a_process_with_plain_blocking_reads_and_writes_gets_all_messages() -> None:
    text = "x" * _MIB
    process, reader, writer = await asyncio.wait_for(
        create_pipe_subprocess(sys.executable, str(_MINIMAL_SERVER), stdout=asyncio.subprocess.DEVNULL), _TIMEOUT
    )
    try:
        peer = JsonRpcPeer(reader, writer)
        peer.start()
        initialized = await asyncio.wait_for(peer.send_request("robot/initialize", {}), _TIMEOUT)
        echoed = await asyncio.wait_for(
            peer.send_request("robot/run_keyword", {"library_token": "minimal", "name": "Echo", "args": [text]}),
            _TIMEOUT,
        )
        await peer.stop()
        code = await asyncio.wait_for(process.wait(), _TIMEOUT)
    finally:
        await _end(process)

    assert initialized["capabilities"] == {"support_exit": True}
    assert echoed == {"result": text}
    assert code == 0


async def test_only_the_first_connection_reaches_the_process(starts: list[_Start]) -> None:
    process, _, writer = await asyncio.wait_for(create_pipe_subprocess(sys.executable, "-c", _ECHO_PEER), _TIMEOUT)
    second: asyncio.Future[tuple[asyncio.StreamReader, asyncio.StreamWriter]] | None = None
    try:
        if sys.platform == "win32":
            # The connected instance keeps the name, so the pipe is busy, and asyncio tries again and again.
            second = asyncio.ensure_future(open_pipe_connection(starts[0].address))
            await asyncio.sleep(1)
            waited = not second.done()
            # The end of the first connection ends the process and the name.
            writer.close()
            await asyncio.wait_for(process.wait(), _TIMEOUT)
            assert waited
            with pytest.raises(FileNotFoundError):
                await asyncio.wait_for(second, _TIMEOUT)
        else:
            await _assert_gone(starts[0].address)
    finally:
        if second is not None and not second.done():
            second.cancel()
        writer.close()
        await _end(process)


async def test_a_process_that_exits_before_it_connects_raises_connection_error(starts: list[_Start]) -> None:
    with pytest.raises(ConnectionError, match="code 3"):
        await asyncio.wait_for(create_pipe_subprocess(sys.executable, "-c", "raise SystemExit(3)"), 10)

    process = starts[0].process
    assert process is not None
    # Reaped, as the caller never gets the process.
    assert process.returncode == 3
    await _assert_gone(starts[0].address)


async def test_a_call_cancelled_while_it_waits_for_the_connection_ends_the_process(starts: list[_Start]) -> None:
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(create_pipe_subprocess(sys.executable, "-c", "import time; time.sleep(60)"), 2)

    process = starts[0].process
    assert process is not None
    assert process.returncode is not None
    await _assert_gone(starts[0].address)


async def test_a_command_that_cannot_be_started_raises_file_not_found_error(starts: list[_Start]) -> None:
    with pytest.raises(FileNotFoundError):
        await create_pipe_subprocess("jsonrpcpeer-test-no-such-command")

    await _assert_gone(starts[0].address)


_REPORT = """
import asyncio, json, os, sys
from jsonrpcpeer import open_pipe_connection

async def main():
    _, writer = await open_pipe_connection(sys.argv[-1].removeprefix("--pipe="))
    writer.write(json.dumps({"cwd": os.getcwd(), "stdin": sys.stdin.read()}).encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()

asyncio.run(main())
"""


async def test_further_arguments_reach_the_start_of_the_process(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    process, reader, writer = await asyncio.wait_for(
        create_pipe_subprocess(sys.executable, "-c", _REPORT, stdin=asyncio.subprocess.DEVNULL, cwd=elsewhere),
        _TIMEOUT,
    )
    try:
        report = json.loads(await asyncio.wait_for(reader.read(), _TIMEOUT))
        code = await asyncio.wait_for(process.wait(), _TIMEOUT)
    finally:
        writer.close()
        await _end(process)

    assert code == 0
    assert Path(report["cwd"]).samefile(elsewhere)
    assert report["stdin"] == ""


class _FakeStartError(Exception):
    """Raised by the fake start of a process."""


@_WINDOWS_ONLY
@pytest.mark.parametrize(
    ("console", "options", "expected"),
    [
        pytest.param(False, {}, "CREATE_NO_WINDOW", id="without_console"),
        pytest.param(True, {}, None, id="with_console"),
        pytest.param(
            False, {"creationflags": "CREATE_NEW_PROCESS_GROUP"}, "CREATE_NEW_PROCESS_GROUP", id="given_flags"
        ),
    ],
)
async def test_a_process_gets_no_window_only_if_the_caller_has_no_console(
    monkeypatch: pytest.MonkeyPatch, console: bool, options: dict[str, str], expected: str | None
) -> None:
    from jsonrpcpeer import _win32_pipes

    seen: dict[str, object] = {}

    async def start(*argv: object, **kwargs: object) -> None:
        seen.update(kwargs)
        raise _FakeStartError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    monkeypatch.setattr(_win32_pipes, "has_console", lambda: console)
    # The flags exist only on Windows, so they are named here, for the type check on other platforms.
    flags = {name: getattr(subprocess, value) for name, value in options.items()}

    with pytest.raises(_FakeStartError):
        await create_pipe_subprocess(sys.executable, **flags)

    assert seen.get("creationflags") == (None if expected is None else getattr(subprocess, expected))
