"""End-to-end tests of the real server over the protocol, without the client.

They show what the client cannot: it drops messages below its log level itself, and it only uses
some of the fields of an error.
"""

import asyncio
import socket
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fake_server import wait_until

from jsonrpcpeer import JsonRpcPeer
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    LOG_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    SET_LOG_LEVEL_NOTIFICATION,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    LogParams,
    RunKeywordErrorMode,
    RunKeywordParams,
    RunKeywordResult,
    SetLogLevelParams,
)

LIBRARY = """\
import logging

from robot.api import ContinuableFailure, FatalError, SkipExecution, logger


class EndToEndLib:
    def log_at_each_level(self):
        logger.trace("library at TRACE")
        logger.debug("library at DEBUG")
        logger.info("library at INFO")

    def log_with_python_logging(self):
        logging.getLogger("library").debug("library at DEBUG")
        logging.getLogger("library").info("library at INFO")

    def fail_with_value_error(self):
        raise ValueError("bad value")

    def fail_with_assertion(self):
        raise AssertionError("boom")

    def skip_the_test(self):
        raise SkipExecution("not today")

    def fail_continuably(self):
        raise ContinuableFailure("go on")

    def fail_fatally(self):
        raise FatalError("stop all")

    def ping(self):
        return "pong"
"""


def _accepts_connections(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), 1).close()
    except OSError:
        return False
    return True


@pytest.fixture(scope="module")
def port(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    directory: Path = tmp_path_factory.mktemp("library")
    (directory / "EndToEndLib.py").write_text(LIBRARY)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port: int = probe.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "robot_jsonrpcremote_server",
            "--port",
            str(free_port),
            "--pythonpath",
            str(directory),
            "EndToEndLib",
        ],
        cwd=directory,
    )
    try:
        wait_until(lambda: _accepts_connections(free_port), timeout=20)
        yield free_port
    finally:
        process.terminate()
        process.wait(10)


class _Session:
    """A connection to the server with the library imported; records the forwarded log messages."""

    def __init__(self, peer: JsonRpcPeer) -> None:
        self.peer = peer
        self.token = ""
        self.messages: list[str] = []

    async def on_log(self, params: LogParams) -> None:
        self.messages.append(params.message)

    async def run_keyword(self, name: str) -> RunKeywordResult:
        return await self.peer.send_request_typed(
            RunKeywordResult, RUN_KEYWORD_REQUEST, RunKeywordParams(library_token=self.token, name=name)
        )

    def library_messages(self) -> list[str]:
        """The forwarded messages without Robot's own TRACE lines about arguments and return values."""
        return [message for message in self.messages if message.startswith("library at ")]


@asynccontextmanager
async def _session(port: int, log_level: str | None = None) -> AsyncIterator[_Session]:
    peer = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", port))
    session = _Session(peer)
    peer.register_notification_handler(LOG_NOTIFICATION, session.on_log)
    peer.start()
    try:
        await peer.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams(log_level=log_level))
        await peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())
        imported = await peer.send_request_typed(
            ImportLibraryResult, IMPORT_LIBRARY_REQUEST, ImportLibraryParams(name="EndToEndLib")
        )
        session.token = imported.token
        yield session
    finally:
        await peer.stop()


async def test_client_at_debug_gets_the_debug_message_and_not_the_trace_message(port: int) -> None:
    async with _session(port, "DEBUG") as session:
        await session.run_keyword("Log At Each Level")

    assert session.library_messages() == ["library at DEBUG", "library at INFO"]


async def test_client_without_a_log_level_gets_the_messages_from_info_on(port: int) -> None:
    async with _session(port) as session:
        await session.run_keyword("Log At Each Level")

    assert session.library_messages() == ["library at INFO"]


async def test_client_that_changes_its_log_level_gets_the_messages_from_the_new_level_on(port: int) -> None:
    async with _session(port, "INFO") as session:
        await session.peer.send_notification(SET_LOG_LEVEL_NOTIFICATION, SetLogLevelParams(log_level="TRACE"))
        await session.run_keyword("Log At Each Level")

    assert session.library_messages() == ["library at TRACE", "library at DEBUG", "library at INFO"]


async def test_log_level_also_applies_to_python_logging(port: int) -> None:
    async with _session(port, "DEBUG") as verbose, _session(port) as quiet:
        await verbose.run_keyword("Log With Python Logging")
        await quiet.run_keyword("Log With Python Logging")

    assert verbose.library_messages() == ["library at DEBUG", "library at INFO"]
    assert quiet.library_messages() == ["library at INFO"]


async def test_clients_at_different_log_levels_get_the_messages_of_their_own_level(port: int) -> None:
    async with _session(port, "TRACE") as verbose, _session(port, "INFO") as quiet:
        await verbose.run_keyword("Log At Each Level")
        await quiet.run_keyword("Log At Each Level")
        await verbose.run_keyword("Log At Each Level")

    assert quiet.library_messages() == ["library at INFO"]
    assert verbose.library_messages() == ["library at TRACE", "library at DEBUG", "library at INFO"] * 2


@pytest.mark.parametrize(
    ("keyword", "message", "error_type", "mode", "raising_line"),
    [
        ("Fail With Value Error", "ValueError: bad value", "ValueError", None, 'raise ValueError("bad value")'),
        ("Fail With Assertion", "boom", "AssertionError", None, 'raise AssertionError("boom")'),
        ("Skip The Test", "not today", "SkipExecution", RunKeywordErrorMode.SKIP, 'raise SkipExecution("not today")'),
        (
            "Fail Continuably",
            "go on",
            "ContinuableFailure",
            RunKeywordErrorMode.CONTINUABLE,
            'raise ContinuableFailure("go on")',
        ),
        (
            "Fail Fatally",
            "FatalError: stop all",
            "FatalError",
            RunKeywordErrorMode.FATAL,
            'raise FatalError("stop all")',
        ),
    ],
)
async def test_failed_keyword_reports_its_message_type_traceback_and_mode(
    port: int, keyword: str, message: str, error_type: str, mode: RunKeywordErrorMode | None, raising_line: str
) -> None:
    async with _session(port) as session:
        error = (await session.run_keyword(keyword)).error

    assert error is not None
    assert (error.message, error.type, error.mode) == (message, error_type, mode)
    assert error.traceback is not None
    assert raising_line in error.traceback
    assert "robot/running" not in error.traceback


async def test_traceback_reaches_the_client_only_in_the_error(port: int) -> None:
    async with _session(port, "DEBUG") as session:
        error = (await session.run_keyword("Fail With Value Error")).error

    assert error is not None
    assert error.traceback is not None
    assert session.messages == []


async def test_server_runs_keywords_after_a_fatal_failure(port: int) -> None:
    async with _session(port) as session:
        await session.run_keyword("Fail Fatally")
        result = await session.run_keyword("Ping")

    assert result.result == "pong"
    assert result.error is None
