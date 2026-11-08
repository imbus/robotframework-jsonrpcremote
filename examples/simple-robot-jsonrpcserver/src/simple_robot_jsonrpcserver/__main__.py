import argparse
import asyncio
import itertools

from jsonrpcpeer import JsonRpcPeer, JsonRpcResponseError, open_pipe_connection, open_stdio_connection
from robot_jsonrpcremote_protocol import (
    ArgumentDefinition,
    ClientEndpoint,
    ExitParams,
    FinalizeLibraryParams,
    FinalizeLibraryResult,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    KeywordDefinition,
    LibraryDefinition,
    LogLevel,
    LogParams,
    RobotJsonRpcErrorCode,
    RunKeywordParams,
    RunKeywordResult,
    ServerCapabilities,
    ServerEndpoint,
    ServerInfo,
    SetLogLevelParams,
    ShutdownParams,
    ShutdownResult,
)


class SimpleRobotServerEndpoint(ServerEndpoint):
    def __init__(self) -> None:
        self.initialize_received: bool = False
        self.initialized_received: bool = False
        self._token_ids = itertools.count()

    async def log(
        self, message: str, level: LogLevel = LogLevel.INFO, console: bool | None = None, html: bool = False
    ) -> None:
        await self.remote(ClientEndpoint).log(LogParams(message=message, level=level, console=console, html=html))

    async def initialize(self, params: InitializeParams) -> InitializeResult:
        print(f"Initializing client: {params}")
        self.initialize_received = True

        return InitializeResult(
            capabilities=ServerCapabilities(support_exit=True, libraries=["SimpleRobotLibrary"]),
            server_info=ServerInfo(name="SimpleRobotServer", version="1.0"),
        )

    async def initialized(self, params: InitializedParams) -> None:
        print(f"Client initialized with params: {params}")
        self.initialized_received = True

    async def set_log_level(self, params: SetLogLevelParams) -> None:
        # This server sends all its log messages: the client logs those from its log level on.
        print(f"Client log level: {params.log_level}")

    async def import_library(self, params: ImportLibraryParams) -> ImportLibraryResult:
        if not self.initialize_received or not self.initialized_received:
            raise JsonRpcResponseError(
                RobotJsonRpcErrorCode.NOT_INITIALIZED,
                "Initialize and Initialized must be received before ImportLibrary.",
            )

        print(f"Importing library: {params.name}")

        return ImportLibraryResult(
            token=f"simple-robot-library-{next(self._token_ids)}",
            definition=LibraryDefinition(
                name="SimpleRobotLibrary",
                doc="A simple robot library exposed via JSON-RPC.",
                keywords=[
                    KeywordDefinition(
                        name="echo",
                        args=[ArgumentDefinition(name="message", type="Any", doc="Message to echo back.")],
                        doc="Echoes the given message.",
                        tags=["example"],
                        source=__file__,
                    )
                ],
            ),
        )

    async def run_keyword(self, params: RunKeywordParams) -> RunKeywordResult:
        if not self.initialize_received or not self.initialized_received:
            raise JsonRpcResponseError(
                RobotJsonRpcErrorCode.NOT_INITIALIZED,
                "Initialize and Initialized must be received before RunKeyword.",
            )

        print(f"Running keyword: {params.name} with args: {params.args} and kwargs: {params.kwargs}")

        await self.log("RUN_KEYWORD_REQUEST processing...", console=True)

        if params.name == "echo":
            message = params.args[0] if params.args else params.kwargs.get("message", "") if params.kwargs else ""
            result = message

            for i in range(3):
                await self.log(f"Echo {i} request received with params: {params}", level=LogLevel.WARN, html=True)
            return RunKeywordResult(result=result)

        raise JsonRpcResponseError(
            RobotJsonRpcErrorCode.KEYWORD_NOT_FOUND,
            f"Keyword '{params.name}' not found in library 'SimpleRobotLibrary'.",
        )

    async def finalize_library(self, params: FinalizeLibraryParams) -> FinalizeLibraryResult:
        print(f"Finalizing library: {params.token}")
        return FinalizeLibraryResult()

    async def shutdown(self, params: ShutdownParams) -> ShutdownResult:
        print("Shutdown requested")
        return ShutdownResult()

    async def exit(self, params: ExitParams) -> None:
        print("Exit received, closing the connection")
        # The end of the input ends the peer's read loop, and the peer closes the connection.
        if self.rpc_peer:
            self.rpc_peer.reader.feed_eof()


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    # The pipes of stdio and a named pipe on Windows have no peer name.
    addr = writer.get_extra_info("peername") or "a pipe"
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


async def run_stdio_server() -> None:
    # From here on, what print() writes goes to stderr, so it cannot get in the way of the messages.
    await handle_client(*await open_stdio_connection())


async def run_pipe_client(address: str) -> None:
    # The client that started this server listens on the pipe: serve it over that one connection.
    await handle_client(*await open_pipe_connection(address))


def run() -> None:
    parser = argparse.ArgumentParser(description="A hand-written Robot Framework remote server.")
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument("--stdio", action="store_true", help="serve one client over stdin and stdout instead of TCP")
    transport.add_argument(
        "--pipe",
        metavar="ADDRESS",
        help="connect to the pipe ADDRESS and serve the client that listens there, instead of TCP; "
        "a client that starts the server for a pipe: URI passes --pipe=ADDRESS",
    )
    args = parser.parse_args()
    if args.pipe is not None:
        serving = run_pipe_client(args.pipe)
    elif args.stdio:
        serving = run_stdio_server()
    else:
        serving = run_server()
    asyncio.run(serving)


if __name__ == "__main__":
    run()
