import asyncio
import datetime
import logging
import uuid
from collections.abc import Generator, Sequence
from typing import Any

from jsonrpcpeer import JsonRpcPeer, rpc_notification, rpc_request
from robot_jsonrpcremote_protocol import (
    EXIT_NOTIFICATION,
    FINALIZE_LIBRARY_REQUEST,
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    SHUTDOWN_REQUEST,
    ExitParams,
    FinalizeLibraryParams,
    FinalizeLibraryResult,
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
    ShutdownParams,
    ShutdownResult,
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
        # Per-endpoint token source: a unique prefix keeps tokens distinct across
        # connections (they share one RobotRemoteContext keyword store), and the
        # per-endpoint counter keeps them readable and unique per import.
        self._endpoint_id = uuid.uuid4().hex[:8]
        self._token_ids = _library_token_id()
        # Tokens of libraries imported on this connection, so they can be finalized
        # on disconnect (the keyword store is shared across connections).
        self._imported_tokens: set[str] = set()
        self._shutdown_received: bool = False
        self._registered = True
        self.loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    def cleanup(self) -> None:
        self._registered = False
        self.initialize_received = False
        self.initialized_received = False
        self.rpc_peer = None

    def log_message(self, message: str, level: str, html: bool, timestamp: datetime.datetime) -> None:
        if not self._registered:
            return
        if level in ("FAIL", "SKIP"):
            return

        # Fire-and-forget: don't block the runner thread waiting for the send.
        # Ordering holds because _send_message writes the whole frame synchronously
        # before its first await, and call_soon_threadsafe scheduling is FIFO.
        asyncio.run_coroutine_threadsafe(
            self.log(message=message, level=_robot_log_level_to_protocol_level(level), html=html),
            self.loop,
        )

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
        token = f"{lib_name}_{self._endpoint_id}_{next(self._token_ids)}"

        # Positional args keep their JSON types; keyword args are forwarded as
        # Robot's "name=value" entries, which Robot resolves and converts using
        # the library's __init__ signature (just like in a Library setting).
        init_args: list[Any] = list(params.args or [])
        init_args += [f"{name}={value}" for name, value in (params.kw_args or {}).items()]

        lib_definition = await self.remote_context.import_library(lib_name, init_args, token, subscriber=self)
        self._imported_tokens.add(token)
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
                    params.library_token, params.name, params.args or [], params.kwargs or {}, subscriber=self
                )
            )
        except Exception as e:
            logger.exception("Error executing keyword '%s': %s", params.name, e)
            return RunKeywordResult(error=RunKeywordError(message=str(e)))

    @rpc_request(FINALIZE_LIBRARY_REQUEST)
    async def finalize_library(self, params: FinalizeLibraryParams) -> FinalizeLibraryResult:
        logger.debug("Finalizing library token: %s", params.token)
        await self.remote_context.finalize_library(params.token, subscriber=self)
        self._imported_tokens.discard(params.token)
        return FinalizeLibraryResult()

    @rpc_request(SHUTDOWN_REQUEST)
    async def shutdown(self, params: ShutdownParams) -> ShutdownResult:
        # Graceful shutdown handshake: the client signals it is about to close.
        # The `exit` notification follows to actually close the connection.
        logger.debug("Shutdown requested by client.")
        self._shutdown_received = True
        return ShutdownResult()

    @rpc_notification(EXIT_NOTIFICATION)
    async def exit(self, params: ExitParams) -> None:
        # Close only this connection (multi-client server). Feeding EOF lets the
        # peer's read loop finish cleanly. We deliberately do NOT call peer.stop()
        # here, since that would cancel this very handler task.
        logger.debug("Exit notification received; closing connection.")
        peer = self.rpc_peer
        if peer is not None:
            peer.running = False
            peer.reader.feed_eof()

    async def finalize_all(self) -> None:
        """Finalize every library still imported on this connection (called on disconnect)."""
        for token in list(self._imported_tokens):
            try:
                await self.remote_context.finalize_library(token, subscriber=self)
            except Exception:
                logger.debug("Failed to finalize library token '%s' on disconnect", token, exc_info=True)
            finally:
                self._imported_tokens.discard(token)
