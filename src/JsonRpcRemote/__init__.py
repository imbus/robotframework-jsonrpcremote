import asyncio
import contextlib
import weakref
from collections.abc import Mapping, Sequence
from enum import Enum
from threading import Event, Thread
from typing import Any
from urllib.parse import urlparse

from robot import result, running
from robot.api import logger
from robot.api.interfaces import Arguments, Tags, TypeHints

from jsonrpcpeer import JsonRpcPeer
from jsonrpcpeer.json_helpers import jsonable_to_value, value_to_jsonable
from jsonrpcpeer.peer import rpc_notification
from robot_jsonrpcremote_protocol import (
    EXIT_NOTIFICATION,
    FINALIZE_LIBRARY_REQUEST,
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    SHUTDOWN_REQUEST,
    ArgumentDefinition,
    ArgumentKind,
    ClientCapabilities,
    ClientInfo,
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
    LogParams,
    RunKeywordParams,
    RunKeywordResult,
    ServerCapabilities,
    ServerInfo,
    ShutdownParams,
    ShutdownResult,
)

from .__version__ import __version__


class _ClientEndpoint:
    def __init__(self) -> None:
        self.callback_loop: asyncio.AbstractEventLoop | None = None
        self.rpc_peer: JsonRpcPeer | None = None
        # Set after initialize/import so the graceful teardown can finalize the
        # library and decide whether the server supports the exit notification.
        self.library_token: str | None = None
        self.server_capabilities: ServerCapabilities | None = None

    @rpc_notification(LOG_NOTIFICATION)
    async def _log_notification(self, params: LogParams) -> None:
        if self.callback_loop is not None:
            self.callback_loop.call_soon_threadsafe(
                logger.write,
                params.message,
                params.level.value if params.level is not None else "INFO",
                params.html or False,
                params.console or False,
            )
        else:
            # TODO: maybe we should use normal print here instead of logger?
            logger.write(
                params.message,
                params.level.value if params.level is not None else "INFO",
                params.html or False,
                params.console or False,
            )

    async def initialize(self) -> InitializeResult:
        if self.rpc_peer is None:
            raise RuntimeError("RPC peer is not initialized yet")

        return await self.rpc_peer.send_request_typed(
            InitializeResult,
            INITIALIZE_REQUEST,
            InitializeParams(
                capabilities=ClientCapabilities(),
                client_info=ClientInfo(name="RobotFramework JsonRpcRemote Client", version=__version__),
            ),
        )

    async def initialized(self) -> None:
        if self.rpc_peer is None:
            raise RuntimeError("RPC peer is not initialized yet")

        await self.rpc_peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())

    async def import_library(
        self, name: str, args: Sequence[Any] | None, kw_args: Mapping[str, Any] | None
    ) -> ImportLibraryResult:
        if self.rpc_peer is None:
            raise RuntimeError("RPC peer is not initialized yet")

        return await self.rpc_peer.send_request_typed(
            ImportLibraryResult,
            IMPORT_LIBRARY_REQUEST,
            ImportLibraryParams(
                name=name,
                args=list(args) if args is not None else None,
                kw_args=dict(kw_args) if kw_args is not None else None,
            ),
        )

    async def run_keyword(
        self, library_token: str, name: str, args: list[Any], named: dict[str, Any]
    ) -> RunKeywordResult:
        if self.rpc_peer is None:
            raise RuntimeError("Peer is not initialized yet")

        return await self.rpc_peer.send_request_typed(
            RunKeywordResult,
            RUN_KEYWORD_REQUEST,
            RunKeywordParams(library_token=library_token, name=name, args=args, kwargs=named),
        )

    async def finalize_library(self, token: str) -> FinalizeLibraryResult:
        if self.rpc_peer is None:
            raise RuntimeError("RPC peer is not initialized yet")

        return await self.rpc_peer.send_request_typed(
            FinalizeLibraryResult,
            FINALIZE_LIBRARY_REQUEST,
            FinalizeLibraryParams(token=token),
        )

    async def shutdown(self) -> ShutdownResult:
        if self.rpc_peer is None:
            raise RuntimeError("RPC peer is not initialized yet")

        return await self.rpc_peer.send_request_typed(ShutdownResult, SHUTDOWN_REQUEST, ShutdownParams())

    async def exit(self) -> None:
        if self.rpc_peer is None:
            raise RuntimeError("RPC peer is not initialized yet")

        await self.rpc_peer.send_notification(EXIT_NOTIFICATION, ExitParams())

    async def graceful_shutdown(self, timeout: float | None) -> None:
        """Best-effort protocol teardown: finalize_library -> shutdown -> exit.

        Runs while a session is being stopped. It must neither hang (the peer has no
        request timeout) nor raise (it may run from a finalizer or with a half-closed
        connection), so every step is time-bounded and its errors are suppressed.
        """
        if self.rpc_peer is None:
            return

        if self.library_token is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.finalize_library(self.library_token), timeout)

        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.shutdown(), timeout)

        if self.server_capabilities is not None and self.server_capabilities.support_exit:
            with contextlib.suppress(Exception):
                await self.exit()


class _SessionResources:
    """Mutable runtime state shared with the session finalizer.

    Held separately from ``_Session`` so the finalizer can reference it without
    capturing ``self`` -- a bound-method/self reference would keep the session
    alive and prevent the finalizer from ever running on garbage collection.
    """

    __slots__ = ("endpoint", "loop", "peer", "thread")

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.peer: JsonRpcPeer | None = None
        self.thread: Thread | None = None
        self.endpoint: _ClientEndpoint | None = None


def _finalize_session(resources: _SessionResources, timeout: float | None) -> None:
    """Stop the peer and join the worker thread. Idempotent and self-free."""
    peer = resources.peer
    loop = resources.loop
    if peer is None or loop is None:
        return
    try:
        # Best-effort graceful protocol teardown (finalize/shutdown/exit) while the
        # connection is still alive, before tearing down the transport.
        endpoint = resources.endpoint
        if endpoint is not None:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(endpoint.graceful_shutdown(timeout), loop).result(timeout)
        asyncio.run_coroutine_threadsafe(peer.stop(), loop).result(timeout)
        if resources.thread is not None:
            resources.thread.join(timeout)
    finally:
        resources.loop = None
        resources.peer = None
        resources.thread = None
        resources.endpoint = None


class _Session:
    def __init__(
        self,
        uri: str,
        library_name: str | None,
        library_args: Sequence[Any] | None,
        library_kw_args: dict[str, Any] | None,
        timeout: float | None = 30.0,
    ) -> None:
        self._uri = uri
        self._library_name = library_name
        self._library_args = library_args
        self._library_kw_args = library_kw_args
        self._timeout = timeout

        self._res = _SessionResources()
        self.initialized = Event()
        self._finalizer = weakref.finalize(self, _finalize_session, self._res, self._timeout)

        self.server_capabilities: ServerCapabilities | None = None
        self.server_info: ServerInfo | None = None
        self.library_definition: LibraryDefinition | None = None
        self.library_token: str | None = None
        self.last_error: BaseException | None = None

        self.client_endpoint = _ClientEndpoint()
        self._res.endpoint = self.client_endpoint

    @property
    def peer(self) -> JsonRpcPeer:
        if self._res.peer is None:
            raise RuntimeError("Peer is not initialized yet")

        return self._res.peer

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._res.loop is None:
            raise RuntimeError("Event loop is not initialized yet")

        return self._res.loop

    def _run(self) -> None:
        asyncio.run(self._run_client())

    async def _run_client(self) -> None:
        self._res.loop = asyncio.get_event_loop()
        try:
            try:
                await self._start_peer()

                await self._initialize_server()
            except Exception as e:
                self.last_error = e
                raise
            finally:
                self.initialized.set()

            try:
                if self._res.peer is not None:
                    await self._res.peer.completion
            except Exception as e:
                self.last_error = e
                raise
            finally:
                await self.close_connection()
        finally:
            self._res.loop = None
            self._res.peer = None
            self._res.thread = None

    async def _start_peer(self) -> None:
        self._res.peer = JsonRpcPeer(*await self.create_connection())

        self._res.peer.attach_endpoint(self.client_endpoint)

        self._res.peer.start()

    async def _initialize_server(self) -> None:
        if self._res.peer is None:
            raise RuntimeError("Peer is not initialized yet")

        initialize_result = await self.client_endpoint.initialize()

        self.server_capabilities = initialize_result.capabilities
        self.server_info = initialize_result.server_info
        self.client_endpoint.server_capabilities = initialize_result.capabilities

        await self.client_endpoint.initialized()

        import_result = await self.client_endpoint.import_library(
            self._library_name or "",
            list(self._library_args) if self._library_args is not None else None,
            self._library_kw_args or None,
        )
        self.library_definition = import_result.definition
        self.library_token = import_result.token
        self.client_endpoint.library_token = import_result.token

    async def create_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        # TODO: support other URI schemes and connection types (e.g., named pipes, sockets, stdio etc.)
        parsed_uri = urlparse(self._uri)
        if parsed_uri.scheme != "tcp":
            raise ValueError(f"Unsupported URI scheme: {parsed_uri.scheme}")

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                parsed_uri.hostname,
                parsed_uri.port if parsed_uri.port is not None else 8271,
            ),
            timeout=self._timeout,
        )

        return reader, writer

    async def close_connection(self) -> None:
        if self._res.peer is not None:
            self._res.peer.reader.feed_eof()
            self._res.peer.writer.close()
            await self._res.peer.writer.wait_closed()

    def start(self) -> None:
        if self._res.thread is not None and self._res.thread.is_alive():
            return

        self._res.thread = Thread(target=self._run, daemon=True)
        self._res.thread.start()

    def stop(self) -> None:
        _finalize_session(self._res, self._timeout)

    async def run_keyword(self, name: str, args: list[Any], named: dict[str, Any]) -> RunKeywordResult:
        try:
            if self.library_token is None:
                raise RuntimeError("Library token is not initialized yet")

            return await self.client_endpoint.run_keyword(self.library_token, name, args, named)
        except Exception as e:
            self.last_error = e
            raise


class SessionScope(Enum):
    TEST = "TEST"
    SUITE = "SUITE"
    GLOBAL = "GLOBAL"


class JsonRpcRemote:
    ROBOT_LIBRARY_VERSION = __version__
    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(
        self,
        uri: str = "tcp://127.0.0.1:8271",
        library_name: str | None = None,
        *library_args: Any,
        rpc_timeout: float = 10.0,
        rpc_scope: SessionScope = SessionScope.SUITE,
        **library_kw_args: Any,
    ) -> None:
        self._uri = uri
        self._timeout = rpc_timeout
        self._scope = rpc_scope

        self._library_name = library_name
        self._library_args = library_args
        self._library_kw_args = library_kw_args or None

        self.__session: _Session | None = None

        self.ROBOT_LIBRARY_LISTENER = self

        self._start_session()

    def __del__(self) -> None:
        self._stop_session()

    def _start_session(self) -> _Session:
        if self.__session is None:
            self.__session = _Session(
                self._uri, self._library_name, self._library_args, self._library_kw_args, self._timeout
            )

            self.__session.start()

            if not self.__session.initialized.wait(self._timeout):
                if self.__session.last_error is not None:
                    raise TimeoutError(
                        "Timeout waiting for JsonRpcRemote session to initialize"
                    ) from self.__session.last_error

                raise TimeoutError("Timeout waiting for JsonRpcRemote session to initialize")

        if self.__session.last_error is not None:
            raise self.__session.last_error
        return self.__session

    @property
    def _session(self) -> _Session:
        return self._start_session()

    def _stop_session(self) -> None:
        if self.__session is not None:
            self.__session.stop()

            self.__session = None

    def _end_test(self, data: running.TestCase, result: result.TestCase) -> None:
        if self._scope == SessionScope.TEST and self.__session is not None:
            self._stop_session()

    def _end_suite(self, data: running.TestSuite, result: result.TestSuite) -> None:
        if self._scope == SessionScope.SUITE and self.__session is not None:
            self._stop_session()

    @property
    def _library_definition(self) -> LibraryDefinition:
        if self._session.library_definition is None:
            raise RuntimeError("Library definition is not available")

        return self._session.library_definition

    def _get_keyword_definition(self, name: str) -> KeywordDefinition:
        keyword = next((kw for kw in self._library_definition.keywords if kw.name == name), None)
        if keyword is None:
            if name == "__init__":
                # Special case for __init__ documentation
                return KeywordDefinition(name="__init__", args=[])
            raise ValueError(f"Keyword '{name}' not available in the library definition of the remote server")

        return keyword

    def get_keyword_names(self) -> Sequence[str]:
        return [keyword.name for keyword in self._library_definition.keywords]

    def get_keyword_documentation(self, name: str) -> str | None:
        if name == "__intro__":
            return self._library_definition.doc

        return self._get_keyword_definition(name).doc

    def get_keyword_arguments(self, name: str) -> Arguments | None:
        keyword = self._get_keyword_definition(name)

        def arg_tuple(arg: ArgumentDefinition) -> str | tuple[str, object]:
            if arg.kind == ArgumentKind.POSITIONAL_ONLY_MARKER:
                return "/"
            if arg.kind == ArgumentKind.NAMED_ONLY_MARKER:
                return "*"

            name = arg.name
            if arg.kind == ArgumentKind.VAR_POSITIONAL:
                name = "*" + name
            elif arg.kind == ArgumentKind.VAR_NAMED:
                name = "**" + name

            if arg.has_default:
                return (name, jsonable_to_value(arg.default))

            return name

        return [arg_tuple(arg) for arg in keyword.args] if keyword.args is not None else None

    def get_keyword_types(self, name: str) -> TypeHints | None:
        type_hints = {}
        for arg in self._get_keyword_definition(name).args:
            if arg.type:
                type_hints[arg.name] = arg.type

        return type_hints if type_hints else None

    def get_keyword_tags(self, name: str) -> Tags | None:
        return self._get_keyword_definition(name).tags

    def get_keyword_source(self, name: str) -> str | None:
        return self._get_keyword_definition(name).source

    async def run_keyword(self, name: str, args: Sequence[Any], named: Mapping[str, Any]) -> Any:
        self._session.client_endpoint.callback_loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(
                    self._session.run_keyword(
                        name,
                        [value_to_jsonable(arg) for arg in args],
                        {key: value_to_jsonable(value) for key, value in named.items()},
                    ),
                    self._session.loop,
                )
            )

            if result.error is not None:
                raise RuntimeError(f"Error executing keyword '{name}': {result.error}")

            return jsonable_to_value(result.result)
        finally:
            self._session.client_endpoint.callback_loop = None
