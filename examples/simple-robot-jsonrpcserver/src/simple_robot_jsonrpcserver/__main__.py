import asyncio
from typing import Any

from robot_jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcremote_protocol import (
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    AnyType,
    ArgumentDefinition,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    KeywordDefinition,
    LibraryDefinition,
    LogParams,
    RunKeywordParams,
    RunKeywordResult,
    ServerInfo,
)


class ClientContext:
    def __init__(self) -> None:
        self.initialize: bool = False
        self.initialized: bool = False


async def initialize(peer: JsonRpcPeer, params: InitializeParams) -> InitializeResult:
    print(f"Initializing client: {params.client_info}")
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
                    args=[ArgumentDefinition(name="message", type=str(AnyType), doc="Message to echo back.")],
                    doc="Echoes the given message.",
                    tags=["example"],
                    source=__file__ + ":19",
                )
            ],
        ),
        server_info=ServerInfo(name="SimpleRobotServer", version="1.0"),
    )


async def initialized(peer: JsonRpcPeer, params: InitializedParams) -> None:
    print(f"Client initialized with params: {params}")
    context = peer.context

    if context is not None:
        context.initialized = True


async def echo(peer: JsonRpcPeer, params: dict[Any, Any]) -> Any:
    print(f"Echoing params: {params}")
    params["echoed"] = True
    await peer.send_notification(
        LOG_NOTIFICATION, LogParams(message="Echo request received, processing...", console=True)
    )

    await asyncio.sleep(1)  # Simulate some processing delay

    for i in range(3):
        await peer.send_notification(
            LOG_NOTIFICATION,
            LogParams(message=f"Echo {i} request received with params: {params}", level="WARN", html=True),
        )

    return params


async def run_keyword(peer: JsonRpcPeer, params: RunKeywordParams) -> RunKeywordResult:
    print(f"Running keyword: {params.name} with args: {params.args} and kwargs: {params.kwargs}")

    if params.name == "echo":
        message = params.args[0]
        result = f"Echo: {message}"
        return RunKeywordResult(result=result, error=None)

    return RunKeywordResult(result=None, error=f"Keyword '{params.name}' not found.")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername")
    print(f"Client connected from {addr}")

    context = ClientContext()
    peer = JsonRpcPeer(reader, writer, context=context)

    # Here you would typically register request and notification handlers
    peer.register_request_handler("echo", echo)

    peer.register_request_handler(
        INITIALIZE_REQUEST,
        initialize,
    )
    peer.register_notification_handler(
        INITIALIZED_NOTIFICATION,
        initialized,
    )

    peer.register_request_handler(RUN_KEYWORD_REQUEST, run_keyword)
    await peer.run()

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
