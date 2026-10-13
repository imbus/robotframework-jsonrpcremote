import asyncio
import concurrent.futures
import contextlib
import shlex
import time
import weakref
from collections.abc import Coroutine, Mapping, Sequence
from enum import Enum
from threading import Event, Lock, Thread
from typing import Any, TypeVar
from urllib.parse import urlparse

from robot import result, running
from robot.api import logger
from robot.api.interfaces import Arguments, Tags, TypeHints
from robot.utils import timestr_to_secs

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

T = TypeVar("T")


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

    __slots__ = ("endpoint", "loop", "peer", "process", "thread")

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.peer: JsonRpcPeer | None = None
        self.thread: Thread | None = None
        self.endpoint: _ClientEndpoint | None = None
        # The spawned server subprocess (stdio transport only).
        self.process: asyncio.subprocess.Process | None = None


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
        # Backstop in case close_connection never reaped the stdio subprocess.
        process = resources.process
        if process is not None and process.returncode is None:
            with contextlib.suppress(Exception):
                process.kill()
        resources.loop = None
        resources.peer = None
        resources.thread = None
        resources.endpoint = None
        resources.process = None


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
        # Exit code of the spawned server (stdio transport), once it has been reaped.
        self.process_returncode: int | None = None

        # Set by stop(): the client closed the session itself, so it was not "lost".
        self.closed_by_client = False
        # Set once the worker thread has fully finished (event loop closed).
        self.ended = Event()
        # Futures of coroutines submitted to the loop that have not completed yet, so
        # they can be failed instead of hanging if the loop ends before running them.
        self._submit_lock = Lock()
        self._submitted: set[concurrent.futures.Future[Any]] = set()

        self.client_endpoint = _ClientEndpoint()
        self._res.endpoint = self.client_endpoint

    @property
    def connection_lost(self) -> bool:
        """True if an established connection ended without the client closing it."""
        if self.closed_by_client or self.library_token is None:
            return False
        peer = self._res.peer
        return peer is None or not peer.running

    def describe_disconnect(self) -> str:
        # Let the worker finish closing the transport (and reaping a stdio server), so
        # the description includes the final error and the server's exit code.
        self.ended.wait(self._timeout)
        reason = (
            f"{type(self.last_error).__name__}: {self.last_error}"
            if self.last_error is not None
            else "the connection was closed by the server"
        )
        if self.process_returncode is not None:
            reason += f" (server process exited with code {self.process_returncode})"
        return reason

    def submit(self, coro: Coroutine[Any, Any, T]) -> "concurrent.futures.Future[T]":
        """Run ``coro`` on the session loop; fails with ConnectionError once the session has ended."""
        with self._submit_lock:
            loop = self._res.loop
            if loop is None or self.ended.is_set():
                coro.close()
                raise ConnectionError(f"Connection to '{self._uri}' is closed")
            try:
                future = asyncio.run_coroutine_threadsafe(coro, loop)
            except RuntimeError as e:  # loop closed in the meantime
                coro.close()
                raise ConnectionError(f"Connection to '{self._uri}' is closed") from e
            self._submitted.add(future)
        future.add_done_callback(self._submitted.discard)
        return future

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
        try:
            asyncio.run(self._run_client())
        except Exception:
            # Already recorded in last_error; the owning JsonRpcRemote reports it.
            pass
        finally:
            with self._submit_lock:
                self.ended.set()
                stranded = [future for future in self._submitted if not future.done()]
            for future in stranded:
                with contextlib.suppress(concurrent.futures.InvalidStateError):
                    future.set_exception(ConnectionError(f"Connection to '{self._uri}' is closed"))

    async def _run_client(self) -> None:
        self._res.loop = asyncio.get_event_loop()
        try:
            try:
                await self._start_peer()

                await self._initialize_server()
            except Exception as e:
                self.last_error = e
                # Release the connection (and reap a spawned stdio server) before
                # signalling the failure, so a failed attempt leaves nothing behind.
                await self.close_connection()
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
        # TODO: support further URI schemes/transports (named pipes, unix sockets, websockets).
        parsed_uri = urlparse(self._uri)

        if parsed_uri.scheme == "tcp":
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    parsed_uri.hostname,
                    parsed_uri.port if parsed_uri.port is not None else 8271,
                ),
                timeout=self._timeout,
            )
            return reader, writer

        if parsed_uri.scheme == "stdio":
            return await self._create_stdio_connection()

        raise ValueError(f"Unsupported URI scheme '{parsed_uri.scheme}'; supported schemes are 'tcp' and 'stdio'.")

    async def _create_stdio_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Spawn the server from a ``stdio:<command>`` URI and talk over its stdin/stdout."""
        rest = self._uri[len("stdio:") :]
        if rest.startswith("//"):
            rest = rest[2:]
        argv = shlex.split(rest)
        if not argv:
            raise ValueError(
                "stdio URI must include a server command, e.g. 'stdio:robot-jsonrpcremote-server --stdio Lib'."
            )

        process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            ),
            timeout=self._timeout,
        )
        self._res.process = process

        assert process.stdout is not None
        assert process.stdin is not None
        return process.stdout, process.stdin

    async def close_connection(self) -> None:
        if self._res.peer is not None:
            self._res.peer.reader.feed_eof()
            self._res.peer.writer.close()
            with contextlib.suppress(Exception):
                await self._res.peer.writer.wait_closed()

        # Closing the writer sent EOF to the server's stdin; reap it, escalating to
        # terminate/kill if it does not exit within the timeout.
        process = self._res.process
        if process is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(process.wait(), self._timeout)
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(process.wait(), self._timeout)
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
            self.process_returncode = process.returncode
            self._res.process = None

    def start(self) -> None:
        if self._res.thread is not None and self._res.thread.is_alive():
            return

        self._res.thread = Thread(target=self._run, daemon=True)
        self._res.thread.start()

    def stop(self) -> None:
        self.closed_by_client = True
        _finalize_session(self._res, self._timeout)

    async def run_keyword(self, name: str, args: list[Any], named: dict[str, Any]) -> RunKeywordResult:
        if self.library_token is None:
            raise RuntimeError("Library token is not initialized yet")

        return await self.client_endpoint.run_keyword(self.library_token, name, args, named)


def _time_option(name: str, value: float | str) -> float:
    """Parse a client time option given as seconds or a Robot time string (e.g. ``"60s"``)."""
    try:
        seconds = float(timestr_to_secs(value, round_to=None))
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid value for '{name}': {value!r}") from e
    if seconds < 0:
        raise ValueError(f"'{name}' must not be negative, got {value!r}.")
    return seconds


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
        reconnect_timeout: float | str = 0,
        reconnect_interval: float | str = 1.0,
        **library_kw_args: Any,
    ) -> None:
        # Set first: __del__ relies on it even if option validation below raises.
        self.__session: _Session | None = None

        self._uri = uri
        self._timeout = rpc_timeout
        self._scope = rpc_scope
        self._reconnect_timeout = _time_option("reconnect_timeout", reconnect_timeout)
        self._reconnect_interval = _time_option("reconnect_interval", reconnect_interval)
        if self._reconnect_timeout > 0 and self._reconnect_interval <= 0:
            raise ValueError("reconnect_interval must be greater than 0 when reconnect_timeout is set.")

        self._library_name = library_name
        self._library_args = library_args
        self._library_kw_args = library_kw_args or None

        self.ROBOT_LIBRARY_LISTENER = self

        self._start_session()

    def __del__(self) -> None:
        self._stop_session()

    def _start_session(self) -> _Session:
        session = self.__session
        if session is not None and session.connection_lost:
            if self._reconnect_timeout <= 0:
                raise ConnectionError(
                    f"Connection to '{self._uri}' was lost: {session.describe_disconnect()}. "
                    "Automatic reconnect is disabled (reconnect_timeout=0)."
                )
            # Drop the dead session first: if reconnecting fails, the next call starts a
            # normal connection attempt instead of failing on this session forever.
            self.__session = None
            self.__session = self._reconnect(session)
            return self.__session

        if session is None:
            session = self.__session = self._connect()
        return session

    def _connect(self) -> _Session:
        """Open a session and run the handshake; a failed attempt is cleaned up and raises."""
        session = _Session(self._uri, self._library_name, self._library_args, self._library_kw_args, self._timeout)
        session.start()

        if not session.initialized.wait(self._timeout):
            session.stop()
            raise TimeoutError("Timeout waiting for JsonRpcRemote session to initialize") from session.last_error

        if session.last_error is not None:
            raise session.last_error
        return session

    def _reconnect(self, lost: _Session) -> _Session:
        reason = lost.describe_disconnect()
        started = time.monotonic()
        deadline = started + self._reconnect_timeout
        attempts = 0
        while True:
            attempts += 1
            try:
                session = self._connect()
            except Exception as e:
                last_error = e
            else:
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ConnectionError(
                    f"Connection to '{self._uri}' was lost ({reason}) and could not be re-established "
                    f"within {self._reconnect_timeout:g}s ({attempts} attempt(s)). "
                    f"Last error: {type(last_error).__name__}: {last_error}"
                ) from last_error
            time.sleep(min(self._reconnect_interval, remaining))

        logger.warn(
            f"Connection to '{self._uri}' was lost ({reason}). Reconnected after "
            f"{time.monotonic() - started:.1f}s ({attempts} attempt(s)); the remote library was imported "
            "again, so its server-side state was reset."
        )
        old = {kw.name for kw in lost.library_definition.keywords} if lost.library_definition else set()
        new = {kw.name for kw in session.library_definition.keywords} if session.library_definition else set()
        if old != new:
            logger.warn(
                "The keywords of the remote library changed after reconnecting "
                f"(added: {', '.join(sorted(new - old)) or '-'}; removed: {', '.join(sorted(old - new)) or '-'})."
            )
        return session

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
        session = self._session
        session.client_endpoint.callback_loop = asyncio.get_event_loop()
        try:
            try:
                result = await asyncio.wrap_future(
                    session.submit(
                        session.run_keyword(
                            name,
                            [value_to_jsonable(arg) for arg in args],
                            {key: value_to_jsonable(value) for key, value in named.items()},
                        )
                    )
                )
            except (ConnectionError, asyncio.CancelledError) as e:
                # A cancellation only means a lost connection if the session died;
                # otherwise it is Robot cancelling the keyword (e.g. a timeout).
                if isinstance(e, asyncio.CancelledError) and not session.connection_lost:
                    raise
                raise ConnectionError(
                    f"Connection to '{self._uri}' was lost while running keyword '{name}' "
                    f"({session.describe_disconnect()}). The keyword is not retried."
                ) from e

            if result.error is not None:
                raise RuntimeError(f"Error executing keyword '{name}': {result.error}")

            return jsonable_to_value(result.result)
        finally:
            session.client_endpoint.callback_loop = None
