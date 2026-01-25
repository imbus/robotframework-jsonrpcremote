import logging
from collections.abc import Sequence

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

from .__version__ import __version__
from ._runner import RobotRemoteContext

logger = logging.getLogger("robot_jsonrpcremote_server.endpoint")


class RobotServerEndpoint:
    def __init__(
        self, remote_context: RobotRemoteContext, libraries: Sequence[str] | None = None, verbose: bool = False
    ) -> None:
        self.remote_context = remote_context
        self.libraries = list(libraries) if libraries is not None else []
        self.verbose = verbose
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
        logger.debug("Initializing client: %s", params)
        self.initialize_received = True

        return InitializeResult(
            capabilities=ServerCapabilities(support_exit=True, libraries=self.libraries),
            server_info=ServerInfo(name="RobotJsonRpcRemoteServer", version=__version__),
        )

    @rpc_notification(INITIALIZED_NOTIFICATION)
    async def initialized(self, params: InitializedParams) -> None:
        logger.debug("Client initialized with params: %s", params)
        self.initialized_received = True

    @rpc_request(IMPORT_LIBRARY_REQUEST)
    async def import_library(self, params: ImportLibraryParams) -> ImportLibraryResult:
        if not self.initialize_received or not self.initialized_received:
            raise RuntimeError("Initialize and Initialized must be received before ImportLibrary.")

        lib_name = params.name
        if lib_name == "":
            if self.libraries:
                lib_name = self.libraries[0]
            else:
                raise RuntimeError(
                    "Library name cannot be empty when there are no libraries defined at server startup."
                )

        if self.libraries and lib_name not in self.libraries:
            raise RuntimeError(f"Library '{lib_name}' is not available.")

        logger.debug("Importing library: %s", lib_name)

        lib_definition = self.remote_context.import_library(lib_name, list(str(a) for a in params.args or []))
        return ImportLibraryResult(
            token="simple-robot-library-token",
            definition=lib_definition,
        )

    @rpc_request(RUN_KEYWORD_REQUEST)
    async def run_keyword(self, params: RunKeywordParams) -> RunKeywordResult:
        if not self.initialize_received or not self.initialized_received:
            raise RuntimeError("Initialize and Initialized must be received before RunKeyword.")

        logger.debug("Running keyword: %s with args: %s and kwargs: %s", params.name, params.args, params.kwargs)

        # if params.name == "echo":
        #     message = params.args[0] if params.args else params.kwargs.get("message", "") if params.kwargs else ""
        #     result = message

        #     for i in range(3):
        #         await self.log(f"Echo {i} request received with params: {params}", level=LogLevel.WARN, html=True)
        #     return RunKeywordResult(result=result)

        return RunKeywordResult(error=RunKeywordError(message=f"Keyword '{params.name}' not found."))
