import asyncio

from jsonrpcpeer import JsonRpcPeer, rpc_notification, rpc_request
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    ArgumentDefinition,
    ImportLibraryParams,
    ImportLibraryResult,
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
    ServerCapabilities,
    ServerInfo,
)


class SimpleRobotServerEndpoint:
    def __init__(self) -> None:
        self.initialize_received: bool = False
        self.initialized_received: bool = False
        self.rpc_peer: JsonRpcPeer | None = None

    async def log(
        self, message: str, level: LogLevel = LogLevel.INFO, console: bool = False, html: bool = False
    ) -> None:
        if self.rpc_peer:
            await self.rpc_peer.send_notification(
                LOG_NOTIFICATION,
                LogParams(message=message, level=level, console=console, html=html),
            )

    @rpc_request(INITIALIZE_REQUEST)
    async def initialize(self, params: InitializeParams) -> InitializeResult:
        print(f"Initializing client: {params}")
        self.initialize_received = True

        return InitializeResult(
            capabilities=ServerCapabilities(support_exit=True, libraries=["SimpleRobotLibrary"]),
            server_info=ServerInfo(name="SimpleRobotServer", version="1.0"),
        )

    @rpc_notification(INITIALIZED_NOTIFICATION)
    async def initialized(self, params: InitializedParams) -> None:
        print(f"Client initialized with params: {params}")
        self.initialized_received = True

    @rpc_request(IMPORT_LIBRARY_REQUEST)
    async def import_library(self, params: ImportLibraryParams) -> ImportLibraryResult:
        if not self.initialize_received or not self.initialized_received:
            raise Exception("Initialize and Initialized must be received before ImportLibrary.")

        print(f"Importing library: {params.name}")

        return ImportLibraryResult(
            token="simple-robot-library-token",
            definition=LibraryDefinition(
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
        )

    @rpc_request(RUN_KEYWORD_REQUEST)
    async def run_keyword(self, params: RunKeywordParams) -> RunKeywordResult:
        if not self.initialize_received or not self.initialized_received:
            raise Exception("Initialize and Initialized must be received before RunKeyword.")

        print(f"Running keyword: {params.name} with args: {params.args} and kwargs: {params.kwargs}")

        await self.log("RUN_KEYWORD_REQUEST processing...", console=True)

        if params.name == "echo":
            message = params.args[0] if params.args else params.kwargs.get("message", "") if params.kwargs else ""
            result = message

            for i in range(3):
                await self.log(f"Echo {i} request received with params: {params}", level=LogLevel.WARN, html=True)
            return RunKeywordResult(result=result)

        return RunKeywordResult(error=RunKeywordError(message=f"Keyword '{params.name}' not found."))


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername")
    print(f"Client connected from {addr}")

    peer = JsonRpcPeer(reader, writer)

    endpoint = SimpleRobotServerEndpoint()
    peer.attach_endpoint(endpoint)

    try:
        await peer.run()
    except Exception as e:
        print(f"Error handling client from {addr}: {type(e).__name__}: {e}")
    finally:
        print(f"Client from {addr} disconnected")


async def run_server() -> None:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 8271)
    async with server:
        print("Server started on 127.0.0.1:8271")
        await server.serve_forever()


def run() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    run()
