"""Unit tests for the server's stdio transport wiring."""

import asyncio
import gc
import os
import sys
import weakref
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    ClientCapabilities,
    ClientInfo,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    RunKeywordParams,
    RunKeywordResult,
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

    monkeypatch.setattr(server_main, "open_stdio_connection", fake_streams)

    server_main._server_started_event.clear()
    server_main._server_stop_event.clear()

    remote_context = RobotRemoteContext()
    task = asyncio.ensure_future(
        server_main.run_stdio_server(remote_context, verbose=False, libraries=None, send_tracebacks=False)
    )

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


async def test_stdio_server_releases_the_peer_of_a_closed_connection(
    loopback_pair: tuple[
        tuple[asyncio.StreamReader, asyncio.StreamWriter], tuple[asyncio.StreamReader, asyncio.StreamWriter]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (server_streams, (client_reader, client_writer)) = loopback_pair

    async def fake_streams() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return server_streams

    monkeypatch.setattr(server_main, "open_stdio_connection", fake_streams)

    server_main._server_started_event.clear()
    server_main._server_stop_event.clear()

    task = asyncio.ensure_future(
        server_main.run_stdio_server(RobotRemoteContext(), verbose=False, libraries=None, send_tracebacks=False)
    )

    for _ in range(100):
        if server_main._server_started_event.is_set():
            break
        await asyncio.sleep(0.01)
    assert server_main._server_started_event.is_set()

    client = JsonRpcPeer(client_reader, client_writer)
    client.start()
    await asyncio.wait_for(
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
    # handle_client() serves TCP connections the same way. Neither the peer nor its endpoint,
    # which refers back to the peer, is bound to a local name here.
    peer_ref = weakref.ref(next(iter(server_main._clients.values()))[0])

    await client.stop()
    client_writer.close()
    await asyncio.wait_for(task, 2)
    await asyncio.sleep(0)

    gc.collect()

    assert peer_ref() is None


@pytest.mark.parametrize("send_tracebacks", [False, True])
async def test_stdio_server_gives_the_option_for_tracebacks_to_the_peer(
    send_tracebacks: bool,
    loopback_pair: tuple[
        tuple[asyncio.StreamReader, asyncio.StreamWriter], tuple[asyncio.StreamReader, asyncio.StreamWriter]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (server_streams, (client_reader, client_writer)) = loopback_pair

    async def fake_streams() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return server_streams

    monkeypatch.setattr(server_main, "open_stdio_connection", fake_streams)

    server_main._server_started_event.clear()
    server_main._server_stop_event.clear()

    task = asyncio.ensure_future(
        server_main.run_stdio_server(
            RobotRemoteContext(), verbose=False, libraries=None, send_tracebacks=send_tracebacks
        )
    )

    client = JsonRpcPeer(client_reader, client_writer)
    client.start()
    await asyncio.wait_for(
        client.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams()),
        2,
    )

    option_of_the_peer = next(iter(server_main._clients.values()))[0].send_tracebacks

    await client.stop()
    client_writer.close()
    await asyncio.wait_for(task, 2)

    assert option_of_the_peer is send_tracebacks


async def test_stdio_server_stops_via_stop_server(
    loopback_pair: tuple[
        tuple[asyncio.StreamReader, asyncio.StreamWriter], tuple[asyncio.StreamReader, asyncio.StreamWriter]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (server_streams, (_client_reader, client_writer)) = loopback_pair

    async def fake_streams() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return server_streams

    monkeypatch.setattr(server_main, "open_stdio_connection", fake_streams)

    server_main._server_started_event.clear()
    server_main._server_stop_event.clear()

    remote_context = RobotRemoteContext()
    task = asyncio.ensure_future(
        server_main.run_stdio_server(remote_context, verbose=False, libraries=None, send_tracebacks=False)
    )

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


async def test_run_server_async_dispatches_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    async def fake_run_stdio_server(
        remote_context: Any, verbose: bool, libraries: Any, send_tracebacks: bool, pickles: bool = True
    ) -> None:
        called["args"] = (remote_context, verbose, libraries, send_tracebacks)

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
        send_tracebacks=True,
    )

    assert called["args"] == (remote_context, True, ["Lib"], True)


_ATESTS_LIBRARIES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "atests", "libraries")


async def _stderr_of_a_stdio_server(keyword: str, text: str) -> str:
    """Run the real server in stdio mode with ``StdioOutputLib``, call ``keyword`` and then Echo; return its stderr.

    The server gets the pipes of subprocess, which are synchronous on Windows, as other parents such as VS Code give.
    """
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "robot_jsonrpcremote_server",
        "--stdio",
        "--pythonpath",
        _ATESTS_LIBRARIES,
        "StdioOutputLib",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stdin is not None
    assert process.stderr is not None
    stderr = asyncio.ensure_future(process.stderr.read())
    peer = JsonRpcPeer(process.stdout, process.stdin)
    peer.start()
    try:
        await asyncio.wait_for(peer.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams()), 20)
        await peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())
        imported = await asyncio.wait_for(
            peer.send_request_typed(
                ImportLibraryResult, IMPORT_LIBRARY_REQUEST, ImportLibraryParams(name="StdioOutputLib")
            ),
            20,
        )

        async def call(name: str, *args: str) -> RunKeywordResult:
            params = RunKeywordParams(library_token=imported.token, name=name, args=list(args))
            return await asyncio.wait_for(peer.send_request_typed(RunKeywordResult, RUN_KEYWORD_REQUEST, params), 20)

        await call(keyword, text)
        # Long enough for a thread that prints after the keyword returned.
        await asyncio.sleep(0.3)
        echo = await call("Echo", "still connected")
    finally:
        # The end of its input stops the server.
        await peer.stop()
        try:
            await asyncio.wait_for(process.wait(), 20)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    assert echo.result == "echo: still connected"
    # The end of its input stopped the server.
    assert process.returncode == 0
    return (await asyncio.wait_for(stderr, 20)).decode(errors="replace")


@pytest.mark.parametrize(
    ("keyword", "text"),
    [
        ("Run Child That Prints", "from-child-process"),
        ("Run Shell Command That Prints", "from-shell-command"),
        ("Write To File Descriptor One", "from-file-descriptor-one"),
        ("Write To The Console", "from-logger-console"),
        ("Print From A Thread Later", "from-thread"),
    ],
)
async def test_output_of_a_keyword_to_stdout_appears_on_the_stderr_of_the_server(keyword: str, text: str) -> None:
    assert text in await _stderr_of_a_stdio_server(keyword, text)
