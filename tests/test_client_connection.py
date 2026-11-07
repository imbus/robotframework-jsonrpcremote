"""Unit tests for the JsonRpcRemote client's transport selection (the stdio happy path
is covered end-to-end by atests/stdio_echo.robot)."""

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import NoReturn

import pytest

from JsonRpcRemote import JsonRpcRemote, _Session

_ROBOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "atests"))
_MINIMAL_SERVER = Path(__file__).resolve().parent / "minimal_stdio_server.py"


def _make_session(uri: str, timeout: float = 5.0) -> _Session:
    return _Session(uri, None, None, None, timeout)


def _stdio_server_command(library: str) -> str:
    # Quoted, so that a path with a space survives the split of the client.
    return shlex.join(
        [sys.executable, "-m", "robot_jsonrpcremote_server", "--stdio", "--pythonpath", _ROBOT_DIR, library]
    )


if sys.platform == "win32":
    import _winapi

    def _pid_exists(pid: int) -> bool:
        """Whether the process still runs; os.kill(pid, 0) would send it a Ctrl+C or end it on Windows."""
        try:
            handle = _winapi.OpenProcess(_winapi.SYNCHRONIZE, False, pid)
        except OSError:
            return False
        try:
            # A process that has ended can still be opened while someone has a handle to it.
            return _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
        finally:
            _winapi.CloseHandle(handle)

else:

    def _pid_exists(pid: int) -> bool:
        """Whether the process still runs."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True


def _wait_pid_gone(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.05)
    return False


async def test_create_connection_rejects_unknown_scheme() -> None:
    session = _make_session("ws://localhost:1234")
    with pytest.raises(ValueError, match="Unsupported URI scheme"):
        await session.create_connection()


async def test_stdio_uri_requires_a_command() -> None:
    session = _make_session("stdio:")
    with pytest.raises(ValueError, match="must include a server command"):
        await session.create_connection()


async def test_stdio_uri_spawns_process_and_returns_streams() -> None:
    command = shlex.join([sys.executable, "-c", "import sys; sys.stdin.read()"])
    session = _make_session(f"stdio:{command}")

    reader, writer = await session.create_connection()
    try:
        assert isinstance(reader, asyncio.StreamReader)
        assert session._res.process is not None
        assert session._res.process.returncode is None
    finally:
        process = session._res.process
        assert process is not None
        process.kill()
        await process.wait()
        # To the end, so that the reader has closed its pipe before the event loop ends.
        await asyncio.wait_for(reader.read(), 10)
        writer.close()


@pytest.mark.skipif(sys.platform != "win32", reason="overlapped pipes exist only on Windows")
async def test_a_stdio_server_gets_overlapped_pipes() -> None:
    # So that a Python server can use I/O completion ports, without a thread per direction.
    code = (
        "import msvcrt, sys; from jsonrpcpeer._win32_pipes import is_overlapped; "
        "print(is_overlapped(msvcrt.get_osfhandle(0)), is_overlapped(msvcrt.get_osfhandle(1)), end='')"
    )
    session = _make_session(f"stdio:{shlex.join([sys.executable, '-c', code])}")

    reader, writer = await session.create_connection()
    try:
        kinds = await asyncio.wait_for(reader.read(), 10)
    finally:
        writer.close()
        process = session._res.process
        assert process is not None
        await asyncio.wait_for(process.wait(), 10)

    assert kinds == b"True True"


async def test_stdio_bad_command_raises_os_error() -> None:
    session = _make_session("stdio:definitely-not-a-real-server-binary-xyz --stdio Lib")
    with pytest.raises(FileNotFoundError):
        await session.create_connection()


def test_stdio_session_spawns_and_reaps_server() -> None:
    session = _Session(f"stdio:{_stdio_server_command('StdioEchoLib')}", "StdioEchoLib", (), None, 20.0)
    session.start()
    assert session.initialized.wait(20)
    assert session.start_error is None

    process = session._res.process
    assert process is not None
    pid = process.pid

    session.stop()

    assert process.returncode is not None
    assert _wait_pid_gone(pid), f"server subprocess {pid} still alive after teardown"


def test_cancelled_close_still_reaps_the_stdio_server(monkeypatch: pytest.MonkeyPatch) -> None:
    unhandled: list[threading.ExceptHookArgs] = []
    monkeypatch.setattr(threading, "excepthook", unhandled.append)
    session = _Session(f"stdio:{_stdio_server_command('StdioEchoLib')}", "StdioEchoLib", (), None, 20.0)
    session.start()
    assert session.initialized.wait(20)
    assert session.start_error is None

    async def cancelled_close() -> None:
        # As when another caller cancels the close future that all callers of wait_closed() share.
        raise asyncio.CancelledError

    monkeypatch.setattr(session.peer.writer, "wait_closed", cancelled_close)
    session.stop()

    assert session.process_returncode is not None
    assert unhandled == []


def test_failed_stdio_handshake_reaps_the_server_before_it_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    # The server only allows StdioEchoLib, so importing another library fails the handshake.
    session = _Session(f"stdio:{_stdio_server_command('StdioEchoLib')}", "NotAllowedLib", (), None, 20.0)
    pids: list[int] = []
    close_connection = session.close_connection

    async def remember_pid_and_close() -> None:
        if session._res.process is not None:
            pids.append(session._res.process.pid)
        await close_connection()

    monkeypatch.setattr(session, "close_connection", remember_pid_and_close)
    session.start()

    assert session.initialized.wait(20)
    assert "not available" in str(session.start_error)
    # Both hold as soon as the failure is reported, without waiting any longer.
    assert session.process_returncode is not None
    assert pids, "the spawned server was never released"
    assert not _pid_exists(pids[0])


class _FakeStartError(Exception):
    """Raised by the fake start of a server."""


@pytest.mark.parametrize(
    ("platform", "command", "argv"),
    [
        pytest.param(
            "win32",
            r"C:\path\to\python.exe -m robot_jsonrpcremote_server --stdio Lib",
            [r"C:\path\to\python.exe", "-m", "robot_jsonrpcremote_server", "--stdio", "Lib"],
            id="path_with_backslashes_on_windows",
        ),
        pytest.param(
            "win32",
            r'"C:\Program Files\tool\server.exe" --stdio',
            [r"C:\Program Files\tool\server.exe", "--stdio"],
            id="quoted_path_with_a_space_on_windows",
        ),
        pytest.param("linux", r"server my\ library", ["server", "my library"], id="backslash_on_posix"),
    ],
)
async def test_a_stdio_command_is_split_as_its_platform_writes_paths(
    monkeypatch: pytest.MonkeyPatch, platform: str, command: str, argv: list[str]
) -> None:
    started: list[tuple[str, ...]] = []

    async def start(*command: str) -> NoReturn:
        started.append(command)
        raise _FakeStartError

    monkeypatch.setattr("JsonRpcRemote.create_stdio_subprocess", start)
    monkeypatch.setattr(sys, "platform", platform)
    session = _make_session(f"stdio:{command}")

    with pytest.raises(_FakeStartError):
        await session.create_connection()

    assert started == [tuple(argv)]


@pytest.mark.skipif(sys.platform != "win32", reason="the event loop policies exist only on Windows")
def test_a_session_runs_when_a_library_has_set_the_selector_policy() -> None:
    # The policy holds for the whole process, so a process of its own sets it.
    script = textwrap.dedent("""
        import asyncio, sys
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        from JsonRpcRemote import JsonRpcRemote

        remote = JsonRpcRemote(sys.argv[1], "MinimalLibrary", rpc_timeout=10)
        try:
            print(asyncio.run(remote.run_keyword("Echo", ["through the proactor"], {})))
        finally:
            remote._stop_session()
    """)
    uri = f"stdio:{shlex.join([sys.executable, str(_MINIMAL_SERVER)])}"

    result = subprocess.run(
        [sys.executable, "-c", script, uri], capture_output=True, text=True, timeout=60, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "through the proactor"


def test_a_stdio_command_with_a_space_in_its_path_reaches_the_server(tmp_path: Path) -> None:
    # A small standalone server, as a server in another language would be started.
    directory = tmp_path / "with space"
    directory.mkdir()
    server = directory / _MINIMAL_SERVER.name
    shutil.copy(_MINIMAL_SERVER, server)
    remote = JsonRpcRemote(f"stdio:{shlex.join([sys.executable, str(server)])}", "MinimalLibrary", rpc_timeout=10)
    try:
        result = asyncio.run(remote.run_keyword("Echo", ["Grüße"], {}))
    finally:
        remote._stop_session()

    assert result == "Grüße"
