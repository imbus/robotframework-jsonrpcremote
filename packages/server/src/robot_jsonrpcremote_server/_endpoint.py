import asyncio
import datetime
import logging
from collections.abc import Generator, Sequence
from typing import Any

from jsonrpcpeer import JsonRpcPeer, rpc_notification, rpc_request
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
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


def _library_token_id() -> Generator[str, Any, Any]:
    i = 0
    while True:
        yield f"jsonrpc_{i}"
        i += 1


def _robot_log_level_to_protocol_level(level: str) -> LogLevel:
    level_map = {
        "TRACE": LogLevel.TRACE,
        "DEBUG": LogLevel.DEBUG,
        "INFO": LogLevel.INFO,
        "WARN": LogLevel.WARN,
        "ERROR": LogLevel.ERROR,
        "CONSOLE": LogLevel.CONSOLE,
        "HTML": LogLevel.HTML,
    }
    return level_map.get(level.upper(), LogLevel.INFO)


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
        self.remote_context.register_log_message_subscriber(self)
        self._registered = True
        self.loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    def cleanup(self) -> None:
        self._registered = False
        self.remote_context.unregister_log_message_subscriber(self)
        self.initialize_received = False
        self.initialized_received = False
        self.rpc_peer = None

    def log_message(self, message: str, level: str, html: bool, timestamp: datetime.datetime) -> None:
        if not self._registered:
            return
        if level in ("FAIL", "SKIP"):
            return

        asyncio.run_coroutine_threadsafe(
            self.log(message=message, level=_robot_log_level_to_protocol_level(level), html=html),
            self.loop,
        ).result()

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
        token = f"{lib_name}_{next(_library_token_id())}"

        lib_definition = await self.remote_context.import_library(
            lib_name, list(str(a) for a in params.args or []), token
        )
        return ImportLibraryResult(
            token=token,
            definition=lib_definition,
        )

    @rpc_request(RUN_KEYWORD_REQUEST)
    async def run_keyword(self, params: RunKeywordParams) -> RunKeywordResult:
        if not self.initialize_received or not self.initialized_received:
            raise RuntimeError("Initialize and Initialized must be received before RunKeyword.")

        try:
            return RunKeywordResult(
                result=await self.remote_context.run_keyword(
                    params.library_token, params.name, params.args or [], params.kwargs or {}
                )
            )
        except Exception as e:
            logger.exception("Error executing keyword '%s': %s", params.name, e)
            return RunKeywordResult(error=RunKeywordError(message=str(e)))
