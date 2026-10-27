"""Unit tests for the server's stdio transport wiring."""

import asyncio
import contextlib
import os
import re
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcremote_protocol import (
    INITIALIZE_REQUEST,
    ClientCapabilities,
    ClientInfo,
    InitializeParams,
    InitializeResult,
)
from robot_jsonrpcremote_server import __main__ as server_main
from robot_jsonrpcremote_server._runner import RobotRemoteContext


@pytest_asyncio.fixture
async def loopback_pair() -> AsyncIterator[
    tuple[tuple[asyncio.StreamReader, asyncio.StreamWriter], tuple[asyncio.StreamReader, asyncio.StreamWriter]]
]:
    """Yield ((server_reader, server_writer), (client_reader, client_writer)) over loopback TCP."""
    holder: dict[str, Any] = {}
    ready = asyncio.Event()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        holder["reader"], holder["writer"] = reader, writer
        ready.set()

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client_reader, client_writer = await asyncio.open_connection("127.0.0.1", port)
    await asyncio.wait_for(ready.wait(), 2)

    try:
        yield (holder["reader"], holder["writer"]), (client_reader, client_writer)
    finally:
        server.close()
        await server.wait_closed()


async def test_stdio_server_initializes_and_stops_runner_on_eof(
    loopback_pair: tuple[
        tuple[asyncio.StreamReader, asyncio.StreamWriter], tuple[asyncio.StreamReader, asyncio.StreamWriter]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (server_streams, (client_reader, client_writer)) = loopback_pair

    async def fake_streams() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return server_streams

    monkeypatch.setattr(server_main, "_stdio_streams", fake_streams)

    server_main._server_started_event.clear()
    server_main._server_stop_event.clear()

    remote_context = RobotRemoteContext()
    task = asyncio.ensure_future(server_main.run_stdio_server(remote_context, verbose=False, libraries=None))

    for _ in range(100):
        if server_main._server_started_event.is_set():
            break
        await asyncio.sleep(0.01)
    assert server_main._server_started_event.is_set()

    client = JsonRpcPeer(client_reader, client_writer)
    client.start()
    result = await asyncio.wait_for(
        client.send_request_typed(
            InitializeResult,
            INITIALIZE_REQUEST,
            InitializeParams(
                capabilities=ClientCapabilities(),
                client_info=ClientInfo(name="test", version="0"),
            ),
        ),
        2,
    )
    assert result.capabilities is not None

    await client.stop()
    client_writer.close()

    await asyncio.wait_for(task, 2)

    assert remote_context._stopped.is_set()
    assert server_main._server_stop_event.is_set()


async def test_stdio_server_stops_via_stop_server(
    loopback_pair: tuple[
        tuple[asyncio.StreamReader, asyncio.StreamWriter], tuple[asyncio.StreamReader, asyncio.StreamWriter]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (server_streams, (_client_reader, client_writer)) = loopback_pair

    async def fake_streams() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return server_streams

    monkeypatch.setattr(server_main, "_stdio_streams", fake_streams)

    server_main._server_started_event.clear()
    server_main._server_stop_event.clear()

    remote_context = RobotRemoteContext()
    task = asyncio.ensure_future(server_main.run_stdio_server(remote_context, verbose=False, libraries=None))

    for _ in range(100):
        if server_main._server_started_event.is_set():
            break
        await asyncio.sleep(0.01)
    assert server_main._server_started_event.is_set()

    server_main.stop_server()

    await asyncio.wait_for(task, 2)

    assert remote_context._stopped.is_set()
    assert server_main._server_stop_event.is_set()

    client_writer.close()


async def test_stdio_streams_raises_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    with pytest.raises(RuntimeError, match="not supported on Windows"):
        await server_main._stdio_streams()


@pytest.mark.skipif(sys.platform != "win32", reason="exercises the real Windows behavior; runs only on Windows")
async def test_stdio_streams_raises_on_windows_native() -> None:
    with pytest.raises(RuntimeError, match="not supported on Windows"):
        await server_main._stdio_streams()


_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the stdio transport is POSIX-only")
_STDIN_ERROR = "stdio mode needs a stdin that can be watched for input, such as a pipe"


@_POSIX_ONLY
@pytest.mark.parametrize("stdin", ["/dev/null", "regular file", "closed"])
async def test_stdio_streams_reject_a_stdin_that_cannot_be_watched(
    stdin: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with contextlib.ExitStack() as files:
        if stdin == "/dev/null":
            monkeypatch.setattr(sys, "stdin", files.enter_context(open(os.devnull)))
        elif stdin == "regular file":
            path = tmp_path / "stdin.txt"
            path.write_text("")
            monkeypatch.setattr(sys, "stdin", files.enter_context(open(path)))
        else:
            monkeypatch.setattr(sys, "stdin", None)

        with pytest.raises(RuntimeError, match=re.escape(_STDIN_ERROR)):
            await server_main._stdio_streams()


@_POSIX_ONLY
async def test_stdio_streams_connect_a_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin_read, stdin_write = os.pipe()
    stdout_read, stdout_write = os.pipe()
    # The transports close these files.
    monkeypatch.setattr(sys, "stdin", open(stdin_read))
    monkeypatch.setattr(sys, "stdout", open(stdout_write, "w"))

    reader, writer = await server_main._stdio_streams()

    # End the input, so the read transport closes itself at EOF.
    os.close(stdin_write)
    assert await asyncio.wait_for(reader.read(), 2) == b""
    # Not wait_closed(): the pipe writer's protocol does not support it.
    writer.close()
    await asyncio.sleep(0)
    os.close(stdout_read)


async def test_run_server_async_dispatches_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    async def fake_run_stdio_server(remote_context: Any, verbose: bool, libraries: Any) -> None:
        called["args"] = (remote_context, verbose, libraries)

    monkeypatch.setattr(server_main, "run_stdio_server", fake_run_stdio_server)

    remote_context = RobotRemoteContext()
    await server_main.run_server_async(
        remote_context=remote_context,
        mode="stdio",
        addresses=["127.0.0.1"],
        port=8271,
        pipe_name="",
        libraries=["Lib"],
        verbose=True,
    )

    assert called["args"] == (remote_context, True, ["Lib"])
