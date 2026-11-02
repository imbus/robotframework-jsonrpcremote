"""End-to-end tests of the real server over the protocol, without the client.

They show what the client cannot: it drops messages below its log level itself, it only uses
some of the fields of an error, and it does not see what the server logs.
"""

import asyncio
import socket
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fake_server import wait_until

from jsonrpcpeer import JsonRpcPeer, JsonRpcResponseError
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
from robot.api.deco import keyword


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

    def fail_with_a_long_message(self):
        raise AssertionError("\\n".join(f"line {number}" for number in range(1, 101)))

    def skip_the_test(self):
        raise SkipExecution("not today")

    def fail_continuably(self):
        raise ContinuableFailure("go on")

    def fail_fatally(self):
        raise FatalError("stop all")

    def ping(self):
        return "pong"

    def return_a_lambda(self):
        return lambda: None

    def repr_of(self, value):
        return repr(value)

    @keyword("Do ${something}")
    def do_something(self, something):
        pass

    @keyword("${someone} Now")
    def someone_now(self, someone):
        pass
"""

MISSING_DEPENDENCY_LIBRARY = """\
import a_module_that_does_not_exist


class MissingDependencyLib:
    pass
"""

FAILING_INIT_LIBRARY = """\
class FailingInitLib:
    def __init__(self):
        raise ValueError("cannot start")
"""

# Files of the server's own code. The module search path may name the package, in a development install.
_FILES_OF_THE_SERVER = ("peer.py", "_endpoint.py", "_runner.py", "__main__.py")


def _accepts_connections(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), 1).close()
    except OSError:
        return False
    return True


@dataclass
class _Server:
    port: int
    stderr: Path

    def log(self) -> str:
        return self.stderr.read_text()

    def last_error(self) -> str:
        """What the server logged last at ERROR level, with the traceback that follows it."""
        return self.log().rpartition("[ERROR] ")[2]


@contextmanager
def _running_server(directory: Path, *arguments: str) -> Iterator[_Server]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port: int = probe.getsockname()[1]
    stderr = directory / f"server-{free_port}.stderr"
    with stderr.open("w") as file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "robot_jsonrpcremote_server",
                "--port",
                str(free_port),
                "--pythonpath",
                str(directory),
                *arguments,
            ],
            cwd=directory,
            stderr=file,
        )
    try:
        wait_until(lambda: _accepts_connections(free_port), timeout=20)
        yield _Server(free_port, stderr)
    finally:
        process.terminate()
        process.wait(10)


@pytest.fixture(scope="module")
def library_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory: Path = tmp_path_factory.mktemp("library")
    (directory / "EndToEndLib.py").write_text(LIBRARY)
    (directory / "MissingDependencyLib.py").write_text(MISSING_DEPENDENCY_LIBRARY)
    (directory / "FailingInitLib.py").write_text(FAILING_INIT_LIBRARY)
    return directory


@pytest.fixture(scope="module")
def server(library_directory: Path) -> Iterator[_Server]:
    with _running_server(library_directory, "EndToEndLib") as running:
        yield running


@pytest.fixture(scope="module")
def server_without_libraries(library_directory: Path) -> Iterator[_Server]:
    with _running_server(library_directory) as running:
        yield running


@pytest.fixture(scope="module")
def server_with_tracebacks(library_directory: Path) -> Iterator[_Server]:
    with _running_server(library_directory, "--send-tracebacks") as running:
        yield running


@pytest.fixture(scope="module")
def port(server: _Server) -> int:
    return server.port


class _Session:
    """A connection to the server; records the forwarded log messages."""

    def __init__(self, peer: JsonRpcPeer) -> None:
        self.peer = peer
        self.token = ""
        self.messages: list[str] = []

    async def on_log(self, params: LogParams) -> None:
        self.messages.append(params.message)

    async def initialize(self, log_level: str | None = None) -> None:
        await self.peer.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams(log_level=log_level))

    async def handshake(self, log_level: str | None = None) -> None:
        await self.initialize(log_level)
        await self.peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())

    async def import_library(self, name: str) -> None:
        imported = await self.peer.send_request_typed(
            ImportLibraryResult, IMPORT_LIBRARY_REQUEST, ImportLibraryParams(name=name)
        )
        self.token = imported.token

    async def run_keyword(self, name: str, args: list[Any] | None = None) -> RunKeywordResult:
        return await self.peer.send_request_typed(
            RunKeywordResult, RUN_KEYWORD_REQUEST, RunKeywordParams(library_token=self.token, name=name, args=args)
        )

    def library_messages(self) -> list[str]:
        """The forwarded messages without Robot's own TRACE lines about arguments and return values."""
        return [message for message in self.messages if message.startswith("library at ")]


@asynccontextmanager
async def _connection(port: int) -> AsyncIterator[_Session]:
    """A connection to the server, before the handshake."""
    peer = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", port))
    session = _Session(peer)
    peer.register_notification_handler(LOG_NOTIFICATION, session.on_log)
    peer.start()
    try:
        yield session
    finally:
        await peer.stop()


@asynccontextmanager
async def _session(port: int, log_level: str | None = None) -> AsyncIterator[_Session]:
    """A connection to the server, after the handshake and with the library imported."""
    async with _connection(port) as session:
        await session.handshake(log_level)
        await session.import_library("EndToEndLib")
        yield session


async def _error_of(call: Awaitable[Any]) -> JsonRpcResponseError:
    with pytest.raises(JsonRpcResponseError) as exc_info:
        await call
    return exc_info.value


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


async def test_failed_keyword_reports_its_whole_message(port: int) -> None:
    async with _session(port) as session:
        error = (await session.run_keyword("Fail With A Long Message")).error

    assert error is not None
    assert error.message == "\n".join(f"line {number}" for number in range(1, 101))


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


async def test_keyword_call_before_the_handshake_is_answered_with_not_initialized(server: _Server) -> None:
    async with _connection(server.port) as session:
        error = await _error_of(session.run_keyword("Ping"))

    assert error.code == -32000
    assert error.message not in server.log()


async def test_library_import_before_the_end_of_the_handshake_is_answered_with_not_initialized(server: _Server) -> None:
    async with _connection(server.port) as session:
        await session.initialize()
        error = await _error_of(session.import_library("EndToEndLib"))

    assert error.code == -32000
    assert error.message not in server.log()


async def test_keyword_that_does_not_exist_is_answered_with_keyword_not_found(server: _Server) -> None:
    async with _session(server.port) as session:
        error = await _error_of(session.run_keyword("Does Not Exist"))

    assert error.code == -32001
    assert error.message == "Keyword 'Does Not Exist' not found in library 'EndToEndLib'."
    assert error.message not in server.log()


async def test_keyword_name_with_several_matches_names_the_library(port: int) -> None:
    async with _session(port) as session:
        error = await _error_of(session.run_keyword("Do It Now"))

    assert error.message == "Multiple keywords named 'Do It Now' found in library 'EndToEndLib'."


async def test_library_that_the_server_does_not_serve_is_refused_with_invalid_params(server: _Server) -> None:
    async with _connection(server.port) as session:
        await session.handshake()
        error = await _error_of(session.import_library("OtherLibrary"))

    assert error.code == -32602
    assert error.message == "Library 'OtherLibrary' is not available."
    assert error.message not in server.log()


async def test_import_without_a_name_is_refused_with_invalid_params(server_without_libraries: _Server) -> None:
    async with _connection(server_without_libraries.port) as session:
        await session.handshake()
        error = await _error_of(session.import_library(""))

    assert error.code == -32602
    assert "name cannot be empty" in error.message
    assert error.message not in server_without_libraries.log()


async def test_library_with_a_missing_dependency_is_reported_with_the_message_of_robot(
    server_without_libraries: _Server,
) -> None:
    async with _connection(server_without_libraries.port) as session:
        await session.handshake()
        error = await _error_of(session.import_library("MissingDependencyLib"))

    assert error.code == -32603
    assert "No module named 'a_module_that_does_not_exist'" in error.message
    assert "    import a_module_that_does_not_exist" in error.message
    assert "PYTHONPATH:" in error.message
    assert not [file for file in _FILES_OF_THE_SERVER if file in error.message]
    assert error.data is None


async def test_library_whose_initialization_fails_is_reported_with_the_message_of_robot(
    server_without_libraries: _Server,
) -> None:
    async with _connection(server_without_libraries.port) as session:
        await session.handshake()
        error = await _error_of(session.import_library("FailingInitLib"))

    assert error.code == -32603
    assert "ValueError: cannot start" in error.message
    assert 'raise ValueError("cannot start")' in error.message
    assert not [file for file in _FILES_OF_THE_SERVER if file in error.message]
    assert error.data is None


async def test_return_value_that_cannot_be_transferred_is_answered_with_a_json_rpc_error(port: int) -> None:
    async with _session(port) as session:
        error = await _error_of(session.run_keyword("Return A Lambda"))

    assert error.code == -32603
    assert "<lambda>" in error.message


async def test_keyword_gets_nested_json_values_unchanged(port: int) -> None:
    async with _session(port) as session:
        result = await session.run_keyword("Repr Of", [{"a": [1, 2]}])

    assert result.error is None
    assert result.result == "{'a': [1, 2]}"


async def test_keyword_gets_a_boolean_as_a_boolean(port: int) -> None:
    async with _session(port) as session:
        result = await session.run_keyword("Repr Of", [True])

    assert result.error is None
    assert result.result == "True"


async def test_wrong_number_of_arguments_is_a_failure_of_the_keyword(port: int) -> None:
    async with _session(port) as session:
        result = await session.run_keyword("Ping", ["unexpected"])

    assert result.error is not None
    assert result.error.message.endswith("expected 0 arguments, got 1.")


async def test_unknown_library_token_is_answered_with_an_error_that_names_it_and_logged_with_its_traceback(
    server_without_libraries: _Server,
) -> None:
    async with _connection(server_without_libraries.port) as session:
        await session.handshake()
        session.token = "nope"
        error = await _error_of(session.run_keyword("Ping"))

    assert error.code == -32603
    assert "'nope'" in error.message
    assert error.data is None
    assert session.messages == []
    logged = server_without_libraries.last_error()
    assert logged.startswith(
        f"The handler of request '{RUN_KEYWORD_REQUEST}' failed\nTraceback (most recent call last):"
    )
    assert error.message in logged


async def test_server_with_the_option_sends_the_traceback_and_logs_it(server_with_tracebacks: _Server) -> None:
    async with _connection(server_with_tracebacks.port) as session:
        await session.handshake()
        session.token = "nope"
        error = await _error_of(session.run_keyword("Ping"))

    assert error.code == -32603
    assert "'nope'" in error.message
    assert str(error.data).startswith("Traceback (most recent call last):")
    assert "_runner.py" in str(error.data)
    logged = server_with_tracebacks.last_error()
    assert logged.startswith(
        f"The handler of request '{RUN_KEYWORD_REQUEST}' failed\nTraceback (most recent call last):"
    )
    assert error.message in logged
