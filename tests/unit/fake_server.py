"""An in-process fake JSON-RPC server for client unit tests (a helper, not collected by pytest).

The server runs on its own thread and event loop: the client blocks the calling thread while
a session starts, so the fake server cannot share the test's loop. Every ``robot/*`` request is
answered by a default handler, unless a test scripted the next answers for its method.
"""

import asyncio
import contextlib
import socket
import struct
import sys
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcremote_protocol import (
    EXIT_NOTIFICATION,
    FINALIZE_LIBRARY_REQUEST,
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    SHUTDOWN_REQUEST,
    ArgumentDefinition,
    ArgumentKind,
    FinalizeLibraryResult,
    ImportLibraryResult,
    InitializeResult,
    KeywordDefinition,
    LibraryDefinition,
    RunKeywordResult,
    ServerCapabilities,
    ServerInfo,
    ShutdownResult,
)

NEVER_ANSWER = object()
"""A scripted answer that leaves the request unanswered."""

_DEFAULT = object()

_REQUESTS = (
    INITIALIZE_REQUEST,
    IMPORT_LIBRARY_REQUEST,
    RUN_KEYWORD_REQUEST,
    FINALIZE_LIBRARY_REQUEST,
    SHUTDOWN_REQUEST,
)


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    """Block until ``condition`` holds; fail the test after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.01)


@dataclass
class FakeConnection:
    """One client connection accepted by the fake server."""

    closed: threading.Event = field(default_factory=threading.Event)


class FakeServer:
    """A scriptable JSON-RPC server speaking the robot protocol, on 127.0.0.1.

    Use it as a context manager. ``stop()`` closes the listener and every connection;
    ``start()`` listens again on the same port. ``close_connections()`` closes only the
    connections and keeps listening.
    """

    def __init__(self, keywords: Iterable[str] = ("Echo",)) -> None:
        self.port = 0
        self.keywords = list(keywords)
        self.connections: list[FakeConnection] = []
        self.requests: list[str] = []
        # The params of each request in ``requests``.
        self.params: list[Any] = []
        self._scripts: defaultdict[str, deque[Any]] = defaultdict(deque)
        self._server: asyncio.AbstractServer | None = None
        self._peers: set[JsonRpcPeer] = set()
        self._clients: set[asyncio.Task[None]] = set()
        # A selector loop on every platform: Windows' default proactor loop shuts a socket down before
        # closing it, so the client would see a clean close instead of the reset of close_connections().
        self._loop = asyncio.SelectorEventLoop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="FakeServer", daemon=True)
        self._thread.start()

    def __enter__(self) -> "FakeServer":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def uri(self) -> str:
        return f"tcp://127.0.0.1:{self.port}"

    def script(self, method: str, *answers: Any) -> None:
        """Answer the next requests for ``method`` with ``answers``, in order.

        An answer is a value to return, an exception to answer with a JSON-RPC error, or
        ``NEVER_ANSWER``. Once the scripted answers are used up, the default handler answers.
        """
        self._scripts[method].extend(answers)

    def start(self) -> None:
        self._run(self._start())

    def stop(self) -> None:
        self._run(self._stop())

    def close_connections(self, reset: bool = False) -> None:
        """Close every connection and keep listening; ``reset`` aborts them with a TCP reset."""
        self._run(self._close_connections(reset))

    def close(self) -> None:
        """Stop the server and end its thread."""
        self.stop()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._loop.close()

    def _run(self, coro: Coroutine[Any, Any, None]) -> None:
        asyncio.run_coroutine_threadsafe(coro, self._loop).result(10)

    async def _start(self) -> None:
        self._server = await asyncio.start_server(self._on_client, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        await self._close_connections(reset=False)
        if server is not None:
            await asyncio.wait_for(server.wait_closed(), 5)

    async def _close_connections(self, reset: bool) -> None:
        for peer in list(self._peers):
            if reset:
                # With a zero linger time, closing the socket sends a reset instead of a FIN.
                linger = struct.pack("HH" if sys.platform == "win32" else "ii", 1, 0)
                peer.writer.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
                peer.writer.transport.abort()
            else:
                peer.writer.close()
        if self._clients:
            await asyncio.wait(list(self._clients), timeout=5)

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._clients.add(task)
        connection = FakeConnection()
        self.connections.append(connection)

        peer = JsonRpcPeer(reader, writer)
        for method in _REQUESTS:
            peer.register_request_handler(method, self._handler(method))
        peer.register_notification_handler(INITIALIZED_NOTIFICATION, self._ignore)
        peer.register_notification_handler(EXIT_NOTIFICATION, self._exit_handler(peer))
        self._peers.add(peer)
        try:
            with contextlib.suppress(Exception):
                await peer.run()
        finally:
            self._peers.discard(peer)
            # Cancels handlers that never answer, so the connection is really done.
            with contextlib.suppress(Exception):
                await peer.stop()
            connection.closed.set()
            self._clients.discard(task)

    def _handler(self, method: str) -> Callable[[Any], Coroutine[Any, Any, Any]]:
        async def handle(params: Any) -> Any:
            self.requests.append(method)
            self.params.append(params)
            scripted = self._scripts[method]
            answer = scripted.popleft() if scripted else _DEFAULT
            if answer is NEVER_ANSWER:
                await asyncio.Event().wait()
            if isinstance(answer, BaseException):
                raise answer
            if answer is _DEFAULT:
                return self._default_answer(method, params)
            return answer

        return handle

    def _default_answer(self, method: str, params: Any) -> Any:
        if method == INITIALIZE_REQUEST:
            return InitializeResult(
                capabilities=ServerCapabilities(support_exit=True),
                server_info=ServerInfo(name="FakeServer", version="0"),
            )
        if method == IMPORT_LIBRARY_REQUEST:
            message = ArgumentDefinition(name="message", kind=ArgumentKind.POSITIONAL_OR_NAMED)
            keywords = [KeywordDefinition(name=name, args=[message]) for name in self.keywords]
            token = f"{params.get('name') or 'FakeLib'}_{len(self.requests)}"
            # Like the real server: the library is named after the token of its import.
            return ImportLibraryResult(token=token, definition=LibraryDefinition(name=token, keywords=keywords))
        if method == RUN_KEYWORD_REQUEST:
            args = params.get("args") or []
            return RunKeywordResult(result=f"echo: {args[0]}" if args else "echo")
        if method == FINALIZE_LIBRARY_REQUEST:
            return FinalizeLibraryResult()
        return ShutdownResult()

    async def _ignore(self, params: Any) -> None:
        pass

    def _exit_handler(self, peer: JsonRpcPeer) -> Callable[[Any], Coroutine[Any, Any, None]]:
        async def exit_connection(params: Any) -> None:
            # Like the real server: end this connection's read loop.
            peer.running = False
            peer.reader.feed_eof()

        return exit_connection
