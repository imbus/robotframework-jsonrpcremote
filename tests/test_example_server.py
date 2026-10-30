"""The hand-written example server handles every message that the client sends in a session."""

import asyncio

from simple_robot_jsonrpcserver.__main__ import handle_client

from jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcremote_protocol import (
    EXIT_NOTIFICATION,
    FINALIZE_LIBRARY_REQUEST,
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    SHUTDOWN_REQUEST,
    ExitParams,
    FinalizeLibraryParams,
    FinalizeLibraryResult,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    ShutdownParams,
    ShutdownResult,
)


async def test_the_example_server_handles_a_whole_session() -> None:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    peer = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", port))
    peer.start()
    try:
        initialize = await peer.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams())
        assert initialize.capabilities is not None
        assert initialize.capabilities.support_exit
        await peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())

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
    finally:
        # Close our end first: wait_closed() waits for every connection of the server.
        await peer.stop()
        server.close()
        await asyncio.wait_for(server.wait_closed(), 5)
