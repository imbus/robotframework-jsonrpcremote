import asyncio
from typing import Any

from robot_jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcpeer.peer import JsonRpcEndpoint
from robot_jsonrpcremote_protocol import (
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    ArgumentDefinition,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    KeywordDefinition,
    LibraryDefinition,
    LogLevel,
    LogParams,
    RunKeywordError,
    RunKeywordParams,
    RunKeywordResult,
    ServerInfo,
)


class ClientContext:
    def __init__(self) -> None:
        self.initialize: bool = False
        self.initialized: bool = False


end_point = JsonRpcEndpoint()


@end_point.request(INITIALIZE_REQUEST)
async def initialize(peer: JsonRpcPeer, params: InitializeParams) -> InitializeResult:
    print(f"Initializing client: {params}")
    context = peer.context

    if context is not None:
        context.initialize = True

    return InitializeResult(
        library_definition=LibraryDefinition(
            name="SimpleRobotLibrary",
            doc="A simple robot library exposed via JSON-RPC.",
            keywords=[
                KeywordDefinition(
                    name="echo",
                    args=[ArgumentDefinition(name="message", type="Any", doc="Message to echo back.")],
                    doc="Echoes the given message.",
                    tags=["example"],
                    source=__file__ + ":19",
                )
            ],
        ),
        server_info=ServerInfo(name="SimpleRobotServer", version="1.0"),
    )


@end_point.notification(INITIALIZED_NOTIFICATION)
async def initialized(peer: JsonRpcPeer, params: InitializedParams) -> None:
    print(f"Client initialized with params: {params}")
    context = peer.context

    if context is not None:
        context.initialized = True


@end_point.request(RUN_KEYWORD_REQUEST)
async def run_keyword(peer: JsonRpcPeer, params: RunKeywordParams) -> RunKeywordResult:
    print(f"Running keyword: {params.name} with args: {params.args} and kwargs: {params.kwargs}")

    await peer.send_notification(LOG_NOTIFICATION, LogParams(message="RUN_KEYWORD_REQUEST processing...", console=True))

    if params.name == "echo":
        message = params.args[0] if params.args else params.kwargs.get("message", "") if params.kwargs else ""
        result = message

        for i in range(3):
            await peer.send_notification(
                LOG_NOTIFICATION,
                LogParams(message=f"Echo {i} request received with params: {params}", level=LogLevel.WARN, html=True),
            )
        return RunKeywordResult(result=result, error=None)

    return RunKeywordResult(result=None, error=RunKeywordError(message=f"Keyword '{params.name}' not found."))


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername")
    print(f"Client connected from {addr}")

    context = ClientContext()
    peer = JsonRpcPeer(reader, writer, context=context)

    end_point.register(peer)

    try:
        await peer.run()
    except Exception as e:
        print(f"Error handling client from {addr}: {e}")

    print(f"Client from {addr} disconnected")


async def run_server() -> None:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 8888)
    async with server:
        print("Server started on 127.0.0.1:8888")
        await server.serve_forever()


def run() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    run()
