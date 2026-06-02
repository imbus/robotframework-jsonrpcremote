"""Unit tests for the server's stdio transport wiring.

These exercise ``run_stdio_server`` over a loopback stream pair substituted for the
real stdin/stdout, so the transport lifecycle -- including the EOF-triggered
``remote_context.stop()`` that lets the blocked main thread exit -- is covered
without a running Robot suite.
"""

import asyncio
from collections.abc import AsyncIterator
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

    # Wait until the transport reports it is up.
    for _ in range(100):
        if server_main._server_started_event.is_set():
            break
        await asyncio.sleep(0.01)
    assert server_main._server_started_event.is_set()

    # Drive a real initialize round-trip over the substituted stream pair.
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

    # Closing the client end sends EOF to the server's stdin-equivalent.
    await client.stop()
    client_writer.close()

    await asyncio.wait_for(task, 2)

    # The single-connection EOF must stop the runner and signal the stop event.
    assert remote_context._stopped.is_set()
    assert server_main._server_stop_event.is_set()


async def test_stdio_streams_raises_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    with pytest.raises(RuntimeError, match="not supported on Windows"):
        await server_main._stdio_streams()


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
