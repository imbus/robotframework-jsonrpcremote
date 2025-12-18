import asyncio
import weakref
from collections.abc import Mapping, Sequence
from enum import Enum
from threading import Event, Thread
from typing import Any
from urllib.parse import urlparse

from robot import result, running
from robot.api import logger
from robot.api.interfaces import Arguments, Tags, TypeHints

from robot_jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcremote_protocol import (
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    ClientCapabilities,
    ClientInfo,
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
)

from .__version__ import __version__


class _Session:
    def __init__(
        self,
        uri: str,
        library_name: str | None,
        library_args: set[Any] | None,
        library_kw_args: dict[str, Any] | None,
        timeout: float = 10.0,
    ) -> None:
        self._uri = uri
        self._library_name = library_name
        self._library_args = library_args
        self._library_kw_args = library_kw_args
        self._timeout = timeout

        self._loop: asyncio.AbstractEventLoop | None = None
        self._peer: JsonRpcPeer | None = None
        self.initialized = Event()
        self.callback_loop: asyncio.AbstractEventLoop | None = None
        self._finalizer = weakref.finalize(self, self.stop)

        self.server_capabilities: ServerCapabilities | None = None
        self.server_info: ServerInfo | None = None
        self.library_definition: LibraryDefinition | None = None
        self.last_error: BaseException | None = None
        self._thread: Thread | None = None

    @property
    def peer(self) -> JsonRpcPeer:
        if self._peer is None:
            raise RuntimeError("Peer is not initialized yet")

        return self._peer

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError("Event loop is not initialized yet")

        return self._loop

    def _run(self) -> None:
        asyncio.run(self._run_client())

    async def _log_notification(self, peer: JsonRpcPeer, params: LogParams) -> None:
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

    async def _run_client(self) -> None:
        self._loop = asyncio.get_event_loop()
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
                if self._peer is not None:
                    await self._peer.completion
            except Exception as e:
                self.last_error = e
                raise
            finally:
                await self.close_connection()
        finally:
            self._loop = None
            self._peer = None
            self._thread = None

    async def _start_peer(self) -> None:
        self._peer = JsonRpcPeer(*await self.create_connection())

        self._peer.register_notification_handler(LOG_NOTIFICATION, self._log_notification)

        self._peer.start()

    async def _initialize_server(self) -> None:
        if self._peer is None:
            raise RuntimeError("Peer is not initialized yet")

        initialize_result = await self._peer.send_request_typed(
            InitializeResult,
            INITIALIZE_REQUEST,
            InitializeParams(
                capabilities=ClientCapabilities(),
                client_info=ClientInfo(name="RobotFramework JsonRpcRemote Client", version="1.0"),
                # TODO: support other initialization options
                # initialization_options=None,
                # trace=None,
                library_name=self._library_name,
                library_args=list(self._library_args) if self._library_args is not None else None,
                library_kw_args=self._library_kw_args,
            ),
        )
        self.server_capabilities = initialize_result.capabilities
        self.server_info = initialize_result.server_info
        self.library_definition = initialize_result.library_definition

        await self._peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())

    async def create_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        # TODO: support other URI schemes and connection types (e.g., named pipes, sockets, stdio etc.)
        parsed_uri = urlparse(self._uri)
        if parsed_uri.scheme != "tcp":
            raise ValueError(f"Unsupported URI scheme: {parsed_uri.scheme}")

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                parsed_uri.hostname,
                parsed_uri.port if parsed_uri.port is not None else 8888,
            ),
            timeout=self._timeout,
        )

        return reader, writer

    async def close_connection(self) -> None:
        if self._peer is not None:
            self._peer.reader.feed_eof()
            self._peer.writer.close()
            await self._peer.writer.wait_closed()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop is None or self._peer is None:
            return

        try:
            asyncio.run_coroutine_threadsafe(self.peer.stop(), self.loop).result(30)

            if self._thread is not None:
                self._thread.join(30)
        finally:
            self._loop = None
            self._peer = None

    async def run_keyword(self, name: str, args: Sequence[Any], named: Mapping[str, Any]) -> RunKeywordResult:
        try:
            if self._peer is None:
                raise RuntimeError("Peer is not initialized yet")

            return await self._peer.send_request_typed(
                RunKeywordResult,
                RUN_KEYWORD_REQUEST,
                RunKeywordParams(name=name, args=list(args), kwargs=dict(named)),
            )
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
        uri: str = "tcp://127.0.0.1:8888",
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
        self._library_kw_args = library_kw_args

        self.__session: _Session | None = None

        self.ROBOT_LIBRARY_LISTENER = self

        self._start_session()

        self._finalizer = weakref.finalize(self, self._stop_session)

    def __del__(self) -> None:
        self._stop_session()

    def _start_session(self) -> _Session:
        if self.__session is None:
            self.__session = _Session(
                self._uri, self._library_name, set(self._library_args), self._library_kw_args, self._timeout
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

        return [arg.name for arg in keyword.args] if keyword.args is not None else None

    def get_keyword_types(self, name: str) -> TypeHints | None:
        type_hints = {}
        for arg in self._get_keyword_definition(name).args:
            if arg.type is not None:
                type_hints[arg.name] = arg.type

        return type_hints if type_hints else None

    def get_keyword_tags(self, name: str) -> Tags | None:
        return self._get_keyword_definition(name).tags

    def get_keyword_source(self, name: str) -> str | None:
        return self._get_keyword_definition(name).source

    async def run_keyword(self, name: str, args: Sequence[Any], named: Mapping[str, Any]) -> Any:
        self._session.callback_loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(self._session.run_keyword(name, args, named), self._session.loop)
            )

            if result.error is not None:
                raise RuntimeError(f"Error executing keyword '{name}': {result.error}")

            return result.result
        finally:
            self._session.callback_loop = None
