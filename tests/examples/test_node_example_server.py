"""The example server in Node.js serves a whole session over TCP, stdio and a pipe, with the codes of the protocol.

The tests start ``examples/node-robot-jsonrpcserver/src/server.ts`` with ``node``. They skip without ``node`` or
without the packages of the example, which ``npm ci`` installs in its folder, except in CI, where they fail.
"""

import asyncio
import re
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager, suppress
from typing import Any

import pytest
from node_example import NODE_EXAMPLE, node_or_skip

from jsonrpcpeer import JsonRpcPeer, JsonRpcResponseError, create_pipe_subprocess, create_stdio_subprocess
from robot_jsonrpcremote_protocol import (
    EXIT_NOTIFICATION,
    FINALIZE_LIBRARY_REQUEST,
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    SET_LOG_LEVEL_NOTIFICATION,
    SHUTDOWN_REQUEST,
    ExitParams,
    FinalizeLibraryParams,
    FinalizeLibraryResult,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    LogParams,
    RobotJsonRpcErrorCode,
    RunKeywordParams,
    RunKeywordResult,
    SetLogLevelParams,
    ShutdownParams,
    ShutdownResult,
)

_SERVER = str(NODE_EXAMPLE / "src" / "server.ts")
_TIMEOUT = 10


@pytest.fixture(scope="module")
def node() -> str:
    """The path of ``node``, if it and the packages of the example are installed."""
    return node_or_skip()


class _Client:
    """A connection to the example server, with the log messages that it has sent."""

    def __init__(self, peer: JsonRpcPeer) -> None:
        self.peer = peer
        self.log_messages: list[str] = []
        peer.register_notification_handler(LOG_NOTIFICATION, self._on_log)

    async def _on_log(self, params: LogParams) -> None:
        self.log_messages.append(params.message)

    async def request[T](self, result_type: type[T], method: str, params: Any) -> T:
        return await asyncio.wait_for(self.peer.send_request_typed(result_type, method, params), _TIMEOUT)

    async def handshake(self) -> InitializeResult:
        initialize = await self.request(InitializeResult, INITIALIZE_REQUEST, InitializeParams())
        await self.peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())
        return initialize

    async def import_library(self) -> ImportLibraryResult:
        return await self.request(ImportLibraryResult, IMPORT_LIBRARY_REQUEST, ImportLibraryParams(name="NodeLibrary"))

    async def run_keyword(self, token: str, name: str, *args: Any) -> RunKeywordResult:
        params = RunKeywordParams(library_token=token, name=name, args=list(args))
        return await self.request(RunKeywordResult, RUN_KEYWORD_REQUEST, params)

    async def whole_session(self) -> RunKeywordResult:
        """A session from robot/initialize to robot/exit, with a call of Echo; returns its result."""
        await self.handshake()
        await self.peer.send_notification(SET_LOG_LEVEL_NOTIFICATION, SetLogLevelParams(log_level="DEBUG"))
        first = await self.import_library()
        second = await self.import_library()
        assert first.token != second.token
        echo = await self.run_keyword(first.token, "Echo", "Grüße")
        await self.request(FinalizeLibraryResult, FINALIZE_LIBRARY_REQUEST, FinalizeLibraryParams(token=first.token))
        await self.request(ShutdownResult, SHUTDOWN_REQUEST, ShutdownParams())
        await self.peer.send_notification(EXIT_NOTIFICATION, ExitParams())
        # The server closes the connection after robot/exit, which ends the peer.
        assert await asyncio.wait_for(self.peer.completion, _TIMEOUT)
        return echo


async def _end(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.kill()
    await process.wait()


_Started = Coroutine[Any, Any, tuple[asyncio.subprocess.Process, asyncio.StreamReader, asyncio.StreamWriter]]


@asynccontextmanager
async def _started_server(starting: _Started) -> AsyncGenerator[tuple[_Client, asyncio.subprocess.Process], None]:
    """A connection to the example server, started by ``create_stdio_subprocess()`` or ``create_pipe_subprocess()``."""
    process, reader, writer = await asyncio.wait_for(starting, _TIMEOUT)
    peer = JsonRpcPeer(reader, writer)
    peer.start()
    try:
        yield _Client(peer), process
    finally:
        await peer.stop()
        await _end(process)


async def _port(stderr: asyncio.StreamReader) -> int:
    """The port of the line ``listening on 127.0.0.1:<port>``, after what Node.js may report before it."""
    while line := await stderr.readline():
        if listening := re.search(rb"listening on 127\.0\.0\.1:(\d+)", line):
            return int(listening[1])
    raise AssertionError("the server ended without listening")


@asynccontextmanager
async def _tcp_client(node: str) -> AsyncGenerator[_Client, None]:
    """A connection to the example server, started on a port that the system chooses."""
    process = await asyncio.create_subprocess_exec(
        node, _SERVER, "--port", "0", stdin=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    assert process.stderr is not None
    output: asyncio.Future[bytes] | None = None
    try:
        port = await asyncio.wait_for(_port(process.stderr), _TIMEOUT)
        # Read the rest of what it reports, so that the pipe never fills.
        output = asyncio.ensure_future(process.stderr.read())
        peer = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", port))
        peer.start()
        try:
            yield _Client(peer)
        finally:
            await peer.stop()
    finally:
        await _end(process)
        if output is not None:
            await asyncio.wait_for(output, _TIMEOUT)


async def test_a_whole_session_over_tcp(node: str) -> None:
    async with _tcp_client(node) as client:
        echo = await client.whole_session()

    assert echo.result == "Grüße"


async def test_a_whole_session_over_stdio(node: str) -> None:
    starting = create_stdio_subprocess(node, _SERVER, "--stdio", stderr=asyncio.subprocess.DEVNULL)
    async with _started_server(starting) as (client, process):
        echo = await client.whole_session()
        # The process ends with the connection.
        code = await asyncio.wait_for(process.wait(), _TIMEOUT)

    assert echo.result == "Grüße"
    assert code == 0


async def test_a_whole_session_over_a_pipe(node: str) -> None:
    # As the client starts it for a pipe: URI, with --pipe=<address> as its last argument.
    starting = create_pipe_subprocess(
        node, _SERVER, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL
    )
    async with _started_server(starting) as (client, process):
        echo = await client.whole_session()
        # The process ends with the connection.
        code = await asyncio.wait_for(process.wait(), _TIMEOUT)

    assert echo.result == "Grüße"
    assert code == 0


async def test_echo_sends_its_log_message_before_its_result(node: str) -> None:
    async with _tcp_client(node) as client:
        await client.handshake()
        library = await client.import_library()
        echo = await client.run_keyword(library.token, "Echo", "hello")
        # Handled in the order of arrival: a log message sent after the result would not be here yet.
        log_messages = list(client.log_messages)

    assert echo.result == "hello"
    assert log_messages == ["Echoing hello"]


async def test_sum_of_gets_a_list_as_plain_json(node: str) -> None:
    async with _tcp_client(node) as client:
        await client.handshake()
        library = await client.import_library()
        result = await client.run_keyword(library.token, "Sum Of", [1, 2, 39])

    sum_of = next(keyword for keyword in library.definition.keywords if keyword.name == "Sum Of")
    assert [arg.type for arg in sum_of.args] == ["list[int]"]
    assert sum_of.return_type == "int"
    assert result.result == 42


async def test_fail_with_answers_with_an_error_and_the_next_call_works(node: str) -> None:
    async with _tcp_client(node) as client:
        await client.handshake()
        library = await client.import_library()
        failed = await client.run_keyword(library.token, "Fail With", "Boom from Node")
        echo = await client.run_keyword(library.token, "Echo", "still there")

    assert failed.result is None
    assert failed.error is not None
    assert (failed.error.message, failed.error.type) == ("Boom from Node", "Error")
    assert echo.result == "still there"


async def test_the_server_states_no_pickle_protocol(node: str) -> None:
    async with _tcp_client(node) as client:
        initialize = await client.handshake()

    assert initialize.capabilities is not None
    assert initialize.capabilities.support_exit
    assert initialize.capabilities.pickle_protocol is None


@pytest.mark.parametrize(
    ("method", "params"),
    [
        (IMPORT_LIBRARY_REQUEST, ImportLibraryParams(name="NodeLibrary")),
        (RUN_KEYWORD_REQUEST, RunKeywordParams(library_token="node-library-0", name="Echo", args=["hello"])),
    ],
)
async def test_a_call_before_robot_initialized_gets_not_initialized(node: str, method: str, params: Any) -> None:
    async with _tcp_client(node) as client:
        # robot/initialize, but not robot/initialized.
        await client.request(InitializeResult, INITIALIZE_REQUEST, InitializeParams())
        with pytest.raises(JsonRpcResponseError) as raised:
            await asyncio.wait_for(client.peer.send_request(method, params), _TIMEOUT)

    assert raised.value.code == RobotJsonRpcErrorCode.NOT_INITIALIZED


async def test_an_unknown_keyword_gets_keyword_not_found(node: str) -> None:
    async with _tcp_client(node) as client:
        await client.handshake()
        library = await client.import_library()
        with pytest.raises(JsonRpcResponseError) as raised:
            await client.run_keyword(library.token, "Gone")

    assert raised.value.code == RobotJsonRpcErrorCode.KEYWORD_NOT_FOUND
    assert raised.value.message == "Keyword 'Gone' not found in library 'NodeLibrary'."
