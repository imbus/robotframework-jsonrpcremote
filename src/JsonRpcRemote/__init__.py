import asyncio
import concurrent.futures
import contextlib
import functools
import inspect
import logging
import shlex
import time
import weakref
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, fields
from enum import Enum
from threading import Event, Lock, Thread
from typing import Any, TypeVar, cast
from urllib.parse import urlparse

from robot import result, running
from robot.api import TypeInfo, logger
from robot.api.interfaces import Arguments, Tags, TypeHints
from robot.utils import secs_to_timestr, timestr_to_secs

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

_T = TypeVar("_T")

# Standard logging: the session's worker thread runs outside Robot Framework's logging.
_logger = logging.getLogger(__name__)

# `logger.write` accepts `console` only since Robot Framework 7.4.
_LOGGER_WRITE_HAS_CONSOLE = "console" in inspect.signature(logger.write).parameters

# How often ending a session checks whether the worker has ended while it waits for a teardown step.
_TEARDOWN_POLL_INTERVAL = 0.05


def _write_log(message: str, level: str, html: bool, console: bool) -> None:
    """Write a log message forwarded by the server, on every supported Robot Framework version."""
    if _LOGGER_WRITE_HAS_CONSOLE:
        logger.write(message, level, html, console)  # type: ignore[arg-type]
        return
    logger.write(message, level, html)  # type: ignore[arg-type]
    if console:
        logger.console(message)


class _LogSink:
    """Hands the server's log messages to Robot Framework on a thread it accepts messages from.

    Messages arrive on a session's worker thread, where Robot Framework drops them. While a keyword call
    runs, they are written on Robot Framework's event loop; otherwise they wait until the test thread
    drains them. One sink serves all sessions of a library instance, so the messages of a session that
    failed to start are not lost with it. The lock keeps the order in which the messages arrived.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: list[tuple[str, str, bool, bool]] = []

    def submit(self, message: str, level: str, html: bool, console: bool) -> None:
        with self._lock:
            if self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(_write_log, message, level, html, console)
                    return
                except RuntimeError:
                    # The loop is closed already; the message waits for the next drain instead.
                    pass
            self._pending.append((message, level, html, console))

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        """On the test thread when a keyword call starts: write the pending messages, then use `loop`."""
        with self._lock:
            self._drain_locked()
            self._loop = loop

    def detach(self) -> None:
        with self._lock:
            self._loop = None

    def drain(self) -> None:
        """Write the pending messages on the calling thread. Never raises."""
        with self._lock:
            self._drain_locked()

    def _drain_locked(self) -> None:
        pending, self._pending = self._pending, []
        for message in pending:
            with contextlib.suppress(Exception):
                _write_log(*message)


def _time_option(name: str, value: float | str) -> float:
    """Parse the option ``name``, given in seconds or as a Robot Framework time string such as ``1 minute``."""
    try:
        seconds: float = timestr_to_secs(value, round_to=None)
    except ValueError as error:
        raise ValueError(f"Invalid value for {name}: {error}") from None
    if seconds < 0:
        raise ValueError(f"Invalid value for {name}: {value!r} is negative.")
    return seconds


def _describe_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__


def _attempts(count: int) -> str:
    return f"{count} attempt" if count == 1 else f"{count} attempts"


def _definition_changes(registered: LibraryDefinition | None, current: LibraryDefinition | None) -> str:
    """Describe how ``current`` differs from ``registered``; empty if they are equal.

    The names are not compared: the server names each imported instance of a library differently.
    """
    if registered is None or current is None:
        return "" if registered is current else "the definition is missing"
    old = {keyword.name: keyword for keyword in registered.keywords}
    new = {keyword.name: keyword for keyword in current.keywords}
    changes = [
        f"{label}: {', '.join(names)}"
        for label, names in (
            ("keywords added", [name for name in new if name not in old]),
            ("keywords removed", [name for name in old if name not in new]),
            ("keywords changed", [name for name in new if name in old and new[name] != old[name]]),
            (
                "library attributes changed",
                [
                    field.name
                    for field in fields(registered)
                    if field.name not in ("name", "keywords")
                    and getattr(registered, field.name) != getattr(current, field.name)
                ],
            ),
        )
        if names
    ]
    if changes:
        return "; ".join(changes)
    return "" if registered.keywords == current.keywords else "the order of the keywords changed"


class _ClientEndpoint:
    def __init__(self, log_sink: _LogSink | None = None) -> None:
        self.log_sink = log_sink if log_sink is not None else _LogSink()
        self.rpc_peer: JsonRpcPeer | None = None
        # Set after initialize/import so the graceful teardown can finalize the
        # library and decide whether the server supports the exit notification.
        self.library_token: str | None = None
        self.server_capabilities: ServerCapabilities | None = None

    @rpc_notification(LOG_NOTIFICATION)
    async def _log_notification(self, params: LogParams) -> None:
        level = params.level.value if params.level is not None else "INFO"
        self.log_sink.submit(params.message, level, params.html or False, params.console or False)

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

    __slots__ = ("ended", "endpoint", "loop", "peer", "process", "thread")

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.peer: JsonRpcPeer | None = None
        self.thread: Thread | None = None
        self.endpoint: _ClientEndpoint | None = None
        # The spawned server subprocess (stdio transport only).
        self.process: asyncio.subprocess.Process | None = None
        # Set once the session's worker has ended; its loop runs nothing more after that.
        self.ended = Event()


def _run_on_loop(
    resources: _SessionResources,
    loop: asyncio.AbstractEventLoop,
    make_coro: Callable[[], Coroutine[Any, Any, Any]],
    timeout: float | None,
) -> None:
    """Run the coroutine ``make_coro`` creates on the worker's ``loop`` and wait for it. Never raises.

    The coroutine is created on the loop, and only while the worker still runs its session there,
    so a loop that is finishing or closed leaves none unawaited. Waiting ends when the coroutine is
    done, when the worker has ended, or after ``timeout``.
    """
    done = Event()
    # Keeps the task alive while it runs; asyncio holds only weak references to tasks.
    tasks: list[asyncio.Task[Any]] = []

    def finished(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            # Retrieved: the teardown is best effort, its errors are of no use to anybody.
            task.exception()
        done.set()

    def start() -> None:
        # On the worker's loop: once the worker has finished its session, there is nothing to tear down.
        if resources.loop is not loop:
            done.set()
            return
        task = loop.create_task(make_coro())
        tasks.append(task)
        task.add_done_callback(finished)

    try:
        loop.call_soon_threadsafe(start)
    except RuntimeError:
        # The loop is closed.
        return
    deadline = None if timeout is None else time.monotonic() + timeout
    while not done.wait(_TEARDOWN_POLL_INTERVAL):
        # A worker that has ended runs nothing more: waiting longer cannot help.
        if resources.ended.is_set() or (deadline is not None and time.monotonic() >= deadline):
            return


def _finalize_session(resources: _SessionResources, timeout: float | None) -> None:
    """Stop the peer and join the worker thread. Idempotent, self-free and never raises.

    Each step is bounded by ``timeout``, since the worker may not process the teardown.
    The stdio backstop and the release of the resources always run.
    """
    peer = resources.peer
    loop = resources.loop
    thread = resources.thread
    try:
        if peer is not None and loop is not None:
            # Best-effort graceful protocol teardown (finalize/shutdown/exit) while the
            # connection is still alive, before tearing down the transport.
            endpoint = resources.endpoint
            if endpoint is not None:
                _run_on_loop(resources, loop, functools.partial(endpoint.graceful_shutdown, timeout), timeout)
            _run_on_loop(resources, loop, peer.stop, timeout)
        if thread is not None:
            # join() raises if the worker thread itself ends the session.
            with contextlib.suppress(Exception):
                thread.join(timeout)
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
        log_sink: _LogSink | None = None,
    ) -> None:
        self._uri = uri
        self._library_name = library_name
        self._library_args = library_args
        self._library_kw_args = library_kw_args
        self._timeout = timeout

        self._res = _SessionResources()
        self.initialized = Event()
        # Set once the worker has ended; from then on, the session runs no more calls. Shared with
        # the resources, so that ending the session stops waiting for a worker that has ended.
        self.ended = self._res.ended
        # Calls handed to the worker that are not done yet; guarded by _calls_lock.
        self._calls: set[concurrent.futures.Future[Any]] = set()
        self._calls_lock = Lock()
        self._finalizer = weakref.finalize(self, _finalize_session, self._res, self._timeout)

        self.server_capabilities: ServerCapabilities | None = None
        self.server_info: ServerInfo | None = None
        self.library_definition: LibraryDefinition | None = None
        self.library_token: str | None = None
        # Why the session failed to start (connecting or the handshake); nothing else.
        self.start_error: BaseException | None = None
        # Why the connection of the started session ended, unless it closed cleanly.
        self.connection_error: BaseException | None = None
        # Exit code of the spawned stdio server, once close_connection() has released it.
        self.process_returncode: int | None = None
        # Set when the client ends the session itself; the end of its connection is then no loss.
        self.closed_by_client = False

        self.client_endpoint = _ClientEndpoint(log_sink)
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
        try:
            asyncio.run(self._run_client())
        except (Exception, asyncio.CancelledError):
            # Raising it would only make the thread print it: the error has already reached
            # the caller it concerns, as start_error or as the error of the failed call, and a
            # cancellation that ends the session concerns no caller.
            _logger.debug("Session for '%s' ended with an error", self._uri, exc_info=True)
        finally:
            self._end()

    def _end(self) -> None:
        """Mark the session as ended and fail the calls that its worker will never run."""
        with self._calls_lock:
            self.ended.set()
            stranded = [call for call in self._calls if not call.done()]
        # Outside the lock: failing a call runs its done-callback, which takes the lock.
        for call in stranded:
            with contextlib.suppress(concurrent.futures.InvalidStateError):
                call.set_exception(self._closed_error())

    async def _run_client(self) -> None:
        self._res.loop = asyncio.get_event_loop()
        try:
            try:
                await self._start_peer()

                await self._initialize_server()
            except Exception as e:
                self.start_error = e
                # Release the connection and a spawned stdio server before the failure is
                # reported, so a failed start leaves nothing behind.
                with contextlib.suppress(Exception):
                    await self.close_connection()
                raise
            finally:
                self.initialized.set()

            try:
                if self._res.peer is not None:
                    try:
                        await self._res.peer.completion
                    except Exception as e:
                        self.connection_error = e
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
                try:
                    await self._res.peer.writer.wait_closed()
                except asyncio.CancelledError:
                    # All callers of wait_closed() share one close future, so another caller can
                    # cancel this wait; the session still releases its server below. Only a
                    # cancellation of the worker itself goes on.
                    task = asyncio.current_task()
                    if task is not None and task.cancelling():
                        raise

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
                # Wait for the killed process too, so its exit code is known.
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(process.wait(), self._timeout)
            self.process_returncode = process.returncode
            self._res.process = None

    def start(self) -> None:
        if self._res.thread is not None and self._res.thread.is_alive():
            return

        self._res.thread = Thread(target=self._run, daemon=True)
        self._res.thread.start()

    def stop(self) -> None:
        # First: the connection ends during the teardown, and that is no loss.
        self.closed_by_client = True
        _finalize_session(self._res, self._timeout)

    @property
    def lost(self) -> bool:
        """Whether the connection of this started session ended without the client closing it."""
        if self.library_token is None or self.closed_by_client:
            return False
        # The read loop stops as soon as the connection ends, before the worker has cleaned up.
        peer = self._res.peer
        return self.ended.is_set() or peer is None or not peer.running

    def loss_cause(self) -> str:
        """Describe why the connection of this lost session ended."""
        # Wait for the worker to finish, bounded: close_connection() records a stdio server's exit code.
        self.ended.wait(self._timeout)
        error = self.connection_error
        cause = "the connection was closed by the server" if error is None else _describe_error(error)
        if self.process_returncode is not None:
            cause += f" (server process exited with code {self.process_returncode})"
        return cause

    def lost_error(self, keyword: str | None = None) -> ConnectionError:
        """The error for a call on this lost session, or for ``keyword``, running when it was lost."""
        running = f" while running keyword '{keyword}'" if keyword is not None else ""
        return ConnectionError(f"Connection to '{self._uri}' was lost{running}: {self.loss_cause()}")

    def submit(self, coro: Coroutine[Any, Any, _T]) -> concurrent.futures.Future[_T]:
        """Run ``coro`` on the session's event loop.

        Raises ``ConnectionError`` if the session has not started or has ended. A call
        that the worker never runs, because it ends first, fails with it, too.
        """
        call: concurrent.futures.Future[_T] | None = None
        with self._calls_lock:
            loop = self._res.loop
            if loop is not None and not self.ended.is_set():
                # Scheduling raises RuntimeError if the loop has been closed meanwhile.
                with contextlib.suppress(RuntimeError):
                    call = asyncio.run_coroutine_threadsafe(coro, loop)
                    self._calls.add(call)
        if call is None:
            # Closed, so that it is not reported as never awaited.
            coro.close()
            raise self._closed_error()
        # Outside the lock: the callback runs right here if the call is already done.
        call.add_done_callback(self._call_done)
        return call

    def _call_done(self, call: concurrent.futures.Future[Any]) -> None:
        with self._calls_lock:
            self._calls.discard(call)

    def _closed_error(self) -> ConnectionError:
        return ConnectionError(f"Connection to '{self._uri}' is closed")

    async def run_keyword(self, name: str, args: list[Any], named: dict[str, Any]) -> RunKeywordResult:
        if self.library_token is None:
            raise RuntimeError("Library token is not initialized yet")

        return await self.client_endpoint.run_keyword(self.library_token, name, args, named)


class SessionScope(Enum):
    TEST = "TEST"
    SUITE = "SUITE"
    GLOBAL = "GLOBAL"


def _scope_option(value: SessionScope | str) -> SessionScope:
    """Convert ``rpc_scope`` the way Robot Framework converts an argument to ``SessionScope``.

    Robot Framework passes a string through for the hint ``SessionScope | str``, and a library
    built on the client may pass one from Python, so the client converts it itself.
    """
    return cast(SessionScope, TypeInfo.from_type_hint(SessionScope).convert(value, name="rpc_scope"))


@dataclass
class _Outage:
    """From a lost connection or a failed connection attempt to the next successful connection."""

    # time.monotonic() when the client began to connect again.
    since: float
    # Why the connection of the last session was lost, until a new session replaces it or its scope ends.
    loss: str | None = None
    failed_attempts: int = 0
    # Set when the connect retry window passed without a connection; from then on, each call tries once.
    window_spent: bool = False


class JsonRpcRemote:
    ROBOT_LIBRARY_VERSION = __version__
    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(
        self,
        uri: str = "tcp://127.0.0.1:8271",
        library_name: str | None = None,
        *library_args: Any,
        rpc_timeout: float | str = 10.0,
        rpc_scope: SessionScope | str = SessionScope.SUITE,
        rpc_connect_retry_timeout: float | str = 0,
        rpc_connect_retry_interval: float | str = 1.0,
        **library_kw_args: Any,
    ) -> None:
        # First: __del__ runs even if the options below are rejected.
        self.__session: _Session | None = None
        self._log_sink = _LogSink()
        self._outage: _Outage | None = None
        # The error for every call after the library definition changed, until the session's scope ends.
        self._incompatible: str | None = None

        self._uri = uri
        self._timeout = _time_option("rpc_timeout", rpc_timeout)
        self._scope = _scope_option(rpc_scope)
        self._retry_timeout = _time_option("rpc_connect_retry_timeout", rpc_connect_retry_timeout)
        self._retry_interval = _time_option("rpc_connect_retry_interval", rpc_connect_retry_interval)
        if self._retry_timeout > 0 and self._retry_interval <= 0:
            raise ValueError("Invalid value for rpc_connect_retry_interval: must be greater than 0 with connect retry.")

        self._library_name = library_name
        self._library_args = library_args
        self._library_kw_args = library_kw_args or None

        self.ROBOT_LIBRARY_LISTENER = self

        # Robot Framework registers the keywords from this definition and never asks again.
        self._registered_definition: LibraryDefinition | None = None
        self._registered_definition = self._start_session().library_definition

    def __del__(self) -> None:
        self._stop_session()

    def _start_session(self) -> _Session:
        try:
            return self._ensure_session()
        finally:
            # Back on the test thread: log messages that arrived meanwhile, e.g. from the import, reach Robot.
            self._log_sink.drain()

    def _ensure_session(self) -> _Session:
        if self._incompatible is not None:
            raise ConnectionError(self._incompatible)

        if self.__session is not None and self.__session.lost:
            if self._retry_timeout <= 0:
                # Kept until it ends with its rpc_scope, so every call until then fails the same way.
                raise self.__session.lost_error()
            # Replaced right away; the cause is kept for the warning after the reconnect.
            lost, self.__session = self.__session, None
            self._outage = _Outage(time.monotonic(), loss=lost.loss_cause())
            lost.stop()

        if self.__session is None:
            session = self._connect_with_retry()
            outage, self._outage = self._outage, None
            if outage is not None and outage.loss is not None:
                self._check_definition(session)
                logger.warn(
                    f"Connection to '{self._uri}' was lost: {outage.loss}. Reconnected after "
                    f"{time.monotonic() - outage.since:.1f}s ({_attempts(outage.failed_attempts + 1)}); "
                    "the remote library was imported again, so its server-side state was reset."
                )
            elif outage is not None and self._retry_timeout > 0:
                logger.info(
                    f"Connected to '{self._uri}' after {time.monotonic() - outage.since:.1f}s "
                    f"({_attempts(outage.failed_attempts + 1)})."
                )
            self.__session = session

        return self.__session

    def _check_definition(self, session: _Session) -> None:
        """Stop ``session`` and raise if its library definition is not the one Robot Framework registered."""
        changes = _definition_changes(self._registered_definition, session.library_definition)
        if changes:
            session.stop()
            self._incompatible = (
                f"Reconnected to '{self._uri}', but the library definition changed since the library was "
                f"imported ({changes}); the library cannot be used until its session ends according to rpc_scope."
            )
            raise ConnectionError(self._incompatible)

    def _connect_with_retry(self) -> _Session:
        """Connect; with connect retry, try again every interval until the window has passed.

        Once a window has passed without a connection, every call makes one attempt until a
        connection succeeds again.
        """
        started = time.monotonic()
        retry = self._retry_timeout > 0 and not (self._outage is not None and self._outage.window_spent)
        deadline = started + self._retry_timeout
        attempts = 0
        while True:
            attempts += 1
            try:
                return self._connect()
            except Exception as error:
                if self._outage is None:
                    self._outage = _Outage(started)
                self._outage.failed_attempts += 1
                if not retry:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._outage.window_spent = True
                    raise ConnectionError(
                        f"Could not connect to '{self._uri}' within {secs_to_timestr(self._retry_timeout)} "
                        f"({_attempts(attempts)}): {_describe_error(error)}"
                    ) from error
            time.sleep(min(self._retry_interval, remaining))

    def _connect(self) -> _Session:
        """Start a new session; return it only once it has started, otherwise raise why it did not."""
        session = _Session(
            self._uri, self._library_name, self._library_args, self._library_kw_args, self._timeout, self._log_sink
        )
        session.start()

        if not session.initialized.wait(self._timeout):
            # Read the cause before stopping: stopping fails the pending handshake on its own.
            cause = session.start_error
            # Leave no worker thread or half-open connection behind. Stopping is best effort:
            # the timeout is the error that matters here.
            with contextlib.suppress(Exception):
                session.stop()
            raise TimeoutError("Timeout waiting for JsonRpcRemote session to initialize") from cause

        if session.start_error is not None:
            raise session.start_error

        return session

    @property
    def _session(self) -> _Session:
        return self._start_session()

    def _stop_session(self) -> None:
        # The session ends: the next one is no reconnect, and its library definition is not checked.
        self._incompatible = None
        if self._outage is not None:
            self._outage.loss = None

        try:
            if self.__session is not None:
                self.__session.stop()

                self.__session = None
        finally:
            # Log messages from the end of the session, e.g. while the server finalized the library.
            self._log_sink.drain()

    # Also without a stored session: a lost connection or a changed library definition ends with the scope.
    def _end_test(self, data: running.TestCase, result: result.TestCase) -> None:
        if self._scope == SessionScope.TEST:
            self._stop_session()

    def _end_suite(self, data: running.TestSuite, result: result.TestSuite) -> None:
        if self._scope == SessionScope.SUITE:
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
        # Read once: the call stays with this session, and the `finally` cannot start a new one.
        session = self._session
        self._log_sink.attach(asyncio.get_event_loop())
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

            if result.error is not None:
                raise RuntimeError(f"Error executing keyword '{name}': {result.error}")

            return jsonable_to_value(result.result)
        except (ConnectionError, asyncio.CancelledError) as error:
            # On a healthy session, raise it unchanged: a CancelledError then means that Robot
            # cancelled the keyword, for example on a timeout.
            if not session.lost:
                raise
            # Not sent again: the server may have run it.
            raise session.lost_error(name) from error
        finally:
            self._log_sink.detach()
