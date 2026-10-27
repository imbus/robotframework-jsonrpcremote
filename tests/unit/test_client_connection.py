"""Unit tests for the JsonRpcRemote client's transport selection (the stdio happy path
is covered end-to-end by tests/robot/stdio_echo.robot)."""

import asyncio
import os
import sys
import time

import pytest

from JsonRpcRemote import _Session

_ROBOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "robot"))


def _make_session(uri: str, timeout: float = 5.0) -> _Session:
    return _Session(uri, None, None, None, timeout)


def _stdio_server_command(library: str) -> str:
    return f"{sys.executable} -m robot_jsonrpcremote_server --stdio --pythonpath {_ROBOT_DIR} {library}"


def _wait_pid_gone(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
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


@pytest.mark.skipif(sys.platform == "win32", reason="the stdio transport is POSIX-only")
async def test_stdio_uri_spawns_process_and_returns_streams() -> None:
    command = f'{sys.executable} -c "import sys; sys.stdin.read()"'
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
        writer.close()


async def test_stdio_bad_command_raises_os_error() -> None:
    session = _make_session("stdio:definitely-not-a-real-server-binary-xyz --stdio Lib")
    with pytest.raises(FileNotFoundError):
        await session.create_connection()


@pytest.mark.skipif(sys.platform == "win32", reason="the stdio server transport is POSIX-only")
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


@pytest.mark.skipif(sys.platform == "win32", reason="the stdio server transport is POSIX-only")
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
    with pytest.raises(ProcessLookupError):
        os.kill(pids[0], 0)
