"""The hand-written example server handles every message that the client sends in a session."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from simple_robot_jsonrpcserver.__main__ import SimpleRobotServerEndpoint, handle_client

from jsonrpcpeer import JsonRpcPeer, JsonRpcResponseError
from robot_jsonrpcremote_protocol import (
    EXIT_NOTIFICATION,
    FINALIZE_LIBRARY_REQUEST,
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    SET_LOG_LEVEL_NOTIFICATION,
    SHUTDOWN_REQUEST,
    ExitParams,
    FinalizeLibraryParams,
    FinalizeLibraryResult,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    RobotJsonRpcErrorCode,
    RunKeywordParams,
    ServerEndpoint,
    SetLogLevelParams,
    ShutdownParams,
    ShutdownResult,
)


@asynccontextmanager
async def _connection_to_the_example_server() -> AsyncIterator[JsonRpcPeer]:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    peer = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", port))
    peer.start()
    try:
        yield peer
    finally:
        # Close our end first: wait_closed() waits for every connection of the server.
        await peer.stop()
        server.close()
        await asyncio.wait_for(server.wait_closed(), 5)


def test_the_example_server_implements_the_definition() -> None:
    assert issubclass(SimpleRobotServerEndpoint, ServerEndpoint)


async def test_the_example_server_handles_a_whole_session(caplog: pytest.LogCaptureFixture) -> None:
    async with _connection_to_the_example_server() as peer:
        initialize = await peer.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams())
        assert initialize.capabilities is not None
        assert initialize.capabilities.support_exit
        await peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())
        await peer.send_notification(SET_LOG_LEVEL_NOTIFICATION, SetLogLevelParams(log_level="DEBUG"))

        params = ImportLibraryParams(name="SimpleRobotLibrary")
        first = await peer.send_request_typed(ImportLibraryResult, IMPORT_LIBRARY_REQUEST, params)
        second = await peer.send_request_typed(ImportLibraryResult, IMPORT_LIBRARY_REQUEST, params)
        assert first.token != second.token

        await peer.send_request_typed(
            FinalizeLibraryResult, FINALIZE_LIBRARY_REQUEST, FinalizeLibraryParams(token=first.token)
        )
        await peer.send_request_typed(ShutdownResult, SHUTDOWN_REQUEST, ShutdownParams())
        await peer.send_notification(EXIT_NOTIFICATION, ExitParams())

        # The server closes the connection after robot/exit, which ends the peer.
        assert await asyncio.wait_for(peer.completion, 5)
        # An error for a notification would mean that the server does not handle it.
        assert "Received error" not in caplog.text


@pytest.mark.parametrize(
    ("method", "params"),
    [
        (IMPORT_LIBRARY_REQUEST, ImportLibraryParams(name="SimpleRobotLibrary")),
        (RUN_KEYWORD_REQUEST, RunKeywordParams(library_token="token", name="echo")),
    ],
)
async def test_the_example_server_answers_a_call_before_the_handshake_with_not_initialized(
    method: str, params: Any
) -> None:
    async with _connection_to_the_example_server() as peer:
        with pytest.raises(JsonRpcResponseError) as raised:
            await peer.send_request(method, params)

    assert raised.value.code == RobotJsonRpcErrorCode.NOT_INITIALIZED


async def test_the_example_server_answers_an_unknown_keyword_with_keyword_not_found() -> None:
    async with _connection_to_the_example_server() as peer:
        await peer.send_request(INITIALIZE_REQUEST, InitializeParams())
        await peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())
        with pytest.raises(JsonRpcResponseError) as raised:
            await peer.send_request(RUN_KEYWORD_REQUEST, RunKeywordParams(library_token="token", name="Gone"))

    assert raised.value.code == RobotJsonRpcErrorCode.KEYWORD_NOT_FOUND
    assert raised.value.message == "Keyword 'Gone' not found in library 'SimpleRobotLibrary'."
