"""Unit tests for the JsonRpcRemote client's transport selection.

The full stdio happy path is covered end-to-end by tests/robot/stdio_echo.robot;
these cover the URI parsing / error branches and the subprocess wiring in isolation.
"""

import asyncio
import sys

import pytest

from JsonRpcRemote import _Session


def _make_session(uri: str, timeout: float = 5.0) -> _Session:
    return _Session(uri, None, None, None, timeout)


async def test_create_connection_rejects_unknown_scheme() -> None:
    session = _make_session("ws://localhost:1234")
    with pytest.raises(ValueError, match="Unsupported URI scheme"):
        await session.create_connection()


async def test_stdio_uri_requires_a_command() -> None:
    session = _make_session("stdio:")
    with pytest.raises(ValueError, match="must include a server command"):
        await session.create_connection()


async def test_stdio_uri_spawns_process_and_returns_streams() -> None:
    # A long-lived child that just blocks on stdin; we never speak the protocol here.
    command = f'{sys.executable} -c "import sys; sys.stdin.read()"'
    session = _make_session(f"stdio:{command}")

    reader, writer = await session.create_connection()
    try:
        assert isinstance(reader, asyncio.StreamReader)
        assert session._res.process is not None
        assert session._res.process.returncode is None  # still running
    finally:
        process = session._res.process
        assert process is not None
        process.kill()
        await process.wait()
        writer.close()
