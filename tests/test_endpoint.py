"""Unit tests for the server endpoint's handlers: the lifecycle, errors, failed keywords and the client's log level.

A stub stands in for ``RobotRemoteContext`` so the handlers can be exercised without a
running Robot suite.
"""

import asyncio
import datetime
import logging
from collections.abc import Awaitable
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from jsonrpcpeer import JsonRpcErrorCode, JsonRpcResponseError
from robot_jsonrpcremote_protocol import (
    ExitParams,
    FinalizeLibraryParams,
    ImportLibraryParams,
    InitializedParams,
    InitializeParams,
    LibraryDefinition,
    LogLevel,
    RobotJsonRpcErrorCode,
    RunKeywordError,
    RunKeywordErrorMode,
    RunKeywordParams,
    SetLogLevelParams,
    ShutdownParams,
)
from robot_jsonrpcremote_server._endpoint import RobotServerEndpoint, _robot_log_level_to_protocol_level
from robot_jsonrpcremote_server._runner import KeywordFailedError, RobotRemoteContext, _shutting_down


class _StubContext:
    """Minimal stand-in for RobotRemoteContext recording finalize calls."""

    def __init__(self) -> None:
        self.finalized: list[str] = []

    async def import_library(self, name: str, args: Any, token: str, subscriber: Any = None) -> LibraryDefinition:
        return LibraryDefinition(name=name, keywords=[])

    async def finalize_library(self, token: str, subscriber: Any = None) -> None:
        self.finalized.append(token)


async def _initialized_endpoint(context: _StubContext, libraries: list[str] | None = None) -> RobotServerEndpoint:
    endpoint = RobotServerEndpoint(remote_context=cast(RobotRemoteContext, context), libraries=libraries)
    await endpoint.initialize(InitializeParams())
    await endpoint.initialized(InitializedParams())
    return endpoint


async def test_import_tracks_token_and_finalize_releases_it() -> None:
    context = _StubContext()
    endpoint = await _initialized_endpoint(context)

    result = await endpoint.import_library(ImportLibraryParams(name="Lib"))
    assert result.token in endpoint._imported_tokens

    await endpoint.finalize_library(FinalizeLibraryParams(token=result.token))
    assert result.token not in endpoint._imported_tokens
    assert context.finalized == [result.token]


async def test_shutdown_sets_flag_and_returns_empty_result() -> None:
    endpoint = await _initialized_endpoint(_StubContext())

    result = await endpoint.shutdown(ShutdownParams())

    assert endpoint._shutdown_received is True
    assert result is not None


async def test_finalize_all_releases_remaining_tokens() -> None:
    context = _StubContext()
    endpoint = await _initialized_endpoint(context)
    r1 = await endpoint.import_library(ImportLibraryParams(name="A"))
    r2 = await endpoint.import_library(ImportLibraryParams(name="B"))

    await endpoint.finalize_all()

    assert endpoint._imported_tokens == set()
    assert set(context.finalized) == {r1.token, r2.token}


class _RejectingFinalizeContext(_StubContext):
    """A stub whose finalize fails for the first library and works for the others."""

    async def finalize_library(self, token: str, subscriber: Any = None) -> None:
        self.finalized.append(token)
        if len(self.finalized) == 1:
            raise RuntimeError("cannot finalize")


async def test_finalize_all_goes_on_after_a_failure() -> None:
    context = _RejectingFinalizeContext()
    endpoint = await _initialized_endpoint(context)
    r1 = await endpoint.import_library(ImportLibraryParams(name="A"))
    r2 = await endpoint.import_library(ImportLibraryParams(name="B"))

    await endpoint.finalize_all()

    assert endpoint._imported_tokens == set()
    assert set(context.finalized) == {r1.token, r2.token}


class _FakeReader:
    def __init__(self) -> None:
        self.eof = False

    def feed_eof(self) -> None:
        self.eof = True


class _FakePeer:
    def __init__(self) -> None:
        self.running = True
        self.reader = _FakeReader()


async def test_exit_closes_connection() -> None:
    endpoint = await _initialized_endpoint(_StubContext())
    peer = _FakePeer()
    endpoint.rpc_peer = cast(Any, peer)

    await endpoint.exit(ExitParams())

    assert peer.running is False
    assert peer.reader.eof is True


async def test_log_and_exit_without_a_connection_do_nothing() -> None:
    endpoint = await _initialized_endpoint(_StubContext())
    assert endpoint.rpc_peer is None

    await endpoint.log("message")
    await endpoint.exit(ExitParams())


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("TRACE", LogLevel.TRACE),
        ("DEBUG", LogLevel.DEBUG),
        ("INFO", LogLevel.INFO),
        ("WARN", LogLevel.WARN),
        ("ERROR", LogLevel.ERROR),
        ("CONSOLE", LogLevel.CONSOLE),
        ("HTML", LogLevel.HTML),
        ("warn", LogLevel.WARN),
        ("UNKNOWN", LogLevel.INFO),
    ],
)
def test_robot_log_levels_map_to_the_levels_of_the_protocol(level: str, expected: LogLevel) -> None:
    assert _robot_log_level_to_protocol_level(level) is expected


async def test_log_messages_for_a_client_that_is_gone_are_not_scheduled() -> None:
    endpoint = await _initialized_endpoint(_StubContext())
    loop = MagicMock()
    endpoint.loop = loop

    endpoint.cleanup()
    endpoint.log_message("message", "INFO", False, datetime.datetime.now(datetime.timezone.utc))

    loop.call_soon_threadsafe.assert_not_called()


async def test_handshake_of_a_client_that_is_gone_counts_as_not_done() -> None:
    endpoint = await _initialized_endpoint(_StubContext())

    endpoint.cleanup()

    assert endpoint.initialize_received is False
    assert endpoint.initialized_received is False
    error = await _error_of(endpoint.run_keyword(RunKeywordParams(library_token="token", name="Keyword")))
    assert error.code == RobotJsonRpcErrorCode.NOT_INITIALIZED


class _BlockingContext(_StubContext):
    """A stub whose keyword calls run until released."""

    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

    async def run_keyword(self, token: str, name: str, args: Any, kwargs: Any, subscriber: Any = None) -> str:
        await self.release.wait()
        return "done"


async def test_wait_idle_returns_once_the_running_handler_finished() -> None:
    context = _BlockingContext()
    endpoint = await _initialized_endpoint(context)
    assert await endpoint.wait_idle(0) is True

    call = asyncio.ensure_future(endpoint.run_keyword(RunKeywordParams(library_token="token", name="Keyword")))
    idle = asyncio.ensure_future(endpoint.wait_idle(5))
    await asyncio.sleep(0.05)
    assert not idle.done()

    context.release.set()

    assert await idle is True
    assert call.done()
    assert call.result().result == "done"


async def test_wait_idle_returns_false_while_a_handler_still_runs() -> None:
    context = _BlockingContext()
    endpoint = await _initialized_endpoint(context)
    call = asyncio.ensure_future(endpoint.run_keyword(RunKeywordParams(library_token="token", name="Keyword")))
    await asyncio.sleep(0)

    assert await endpoint.wait_idle(0.1) is False

    context.release.set()
    await call


async def test_wait_idle_returns_at_once_before_the_first_request() -> None:
    endpoint = RobotServerEndpoint(remote_context=cast(RobotRemoteContext, _StubContext()))

    assert await endpoint.wait_idle(0) is True


class _ReleasedByNameContext(_StubContext):
    """A stub whose keyword calls run until the keyword of their name is released."""

    def __init__(self, *names: str) -> None:
        super().__init__()
        self.releases = {name: asyncio.Event() for name in names}

    async def run_keyword(self, token: str, name: str, args: Any, kwargs: Any, subscriber: Any = None) -> str:
        await self.releases[name].wait()
        return "done"


async def test_wait_idle_waits_for_the_last_of_two_running_handlers() -> None:
    context = _ReleasedByNameContext("First", "Second")
    endpoint = await _initialized_endpoint(context)
    first = asyncio.ensure_future(endpoint.run_keyword(RunKeywordParams(library_token="token", name="First")))
    second = asyncio.ensure_future(endpoint.run_keyword(RunKeywordParams(library_token="token", name="Second")))
    await asyncio.sleep(0)

    context.releases["First"].set()
    await first
    assert await endpoint.wait_idle(0) is False

    context.releases["Second"].set()
    await second
    assert await endpoint.wait_idle(0) is True


class _FailingContext(_StubContext):
    """A stub whose keyword calls raise ``error``."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def run_keyword(self, token: str, name: str, args: Any, kwargs: Any, subscriber: Any = None) -> str:
        raise self.error


async def test_failed_keyword_is_answered_with_its_error_and_logged_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    error = RunKeywordError(
        message="stop all", type="FatalError", traceback="the trace", mode=RunKeywordErrorMode.FATAL
    )
    endpoint = await _initialized_endpoint(_FailingContext(KeywordFailedError(error)))

    with caplog.at_level(logging.DEBUG, logger="robot_jsonrpcremote_server.endpoint"):
        result = await endpoint.run_keyword(RunKeywordParams(library_token="token", name="Keyword"))

    assert result.error == error
    assert [(record.levelno, record.getMessage()) for record in caplog.records if "Keyword" in record.getMessage()] == [
        (logging.DEBUG, "Keyword 'Keyword' failed: stop all")
    ]


async def test_other_exception_leaves_run_keyword() -> None:
    endpoint = await _initialized_endpoint(_FailingContext(ValueError("bad value")))

    with pytest.raises(ValueError, match=r"^bad value$"):
        await endpoint.run_keyword(RunKeywordParams(library_token="token", name="Keyword"))


async def test_error_of_a_stopping_server_leaves_run_keyword() -> None:
    error = _shutting_down()
    endpoint = await _initialized_endpoint(_FailingContext(error))

    assert await _error_of(endpoint.run_keyword(RunKeywordParams(library_token="token", name="Keyword"))) is error
    assert (error.code, error.message) == (JsonRpcErrorCode.INTERNAL_ERROR, "server is shutting down")


async def _error_of(call: Awaitable[Any]) -> JsonRpcResponseError:
    with pytest.raises(JsonRpcResponseError) as exc_info:
        await call
    return exc_info.value


_INCOMPLETE_HANDSHAKES = [(False, False), (True, False), (False, True)]


async def _endpoint_after_handshake(initialize: bool, initialized: bool) -> RobotServerEndpoint:
    endpoint = RobotServerEndpoint(remote_context=cast(RobotRemoteContext, _StubContext()))
    if initialize:
        await endpoint.initialize(InitializeParams())
    if initialized:
        await endpoint.initialized(InitializedParams())
    return endpoint


@pytest.mark.parametrize(("initialize", "initialized"), _INCOMPLETE_HANDSHAKES)
async def test_keyword_call_before_the_end_of_the_handshake_is_answered_with_not_initialized(
    initialize: bool, initialized: bool
) -> None:
    endpoint = await _endpoint_after_handshake(initialize, initialized)

    error = await _error_of(endpoint.run_keyword(RunKeywordParams(library_token="token", name="Keyword")))

    assert error.code == RobotJsonRpcErrorCode.NOT_INITIALIZED


@pytest.mark.parametrize(("initialize", "initialized"), _INCOMPLETE_HANDSHAKES)
async def test_library_import_before_the_end_of_the_handshake_is_answered_with_not_initialized(
    initialize: bool, initialized: bool
) -> None:
    endpoint = await _endpoint_after_handshake(initialize, initialized)

    error = await _error_of(endpoint.import_library(ImportLibraryParams(name="Lib")))

    assert error.code == RobotJsonRpcErrorCode.NOT_INITIALIZED


async def test_import_of_a_library_that_the_server_does_not_serve_is_answered_with_invalid_params() -> None:
    endpoint = await _initialized_endpoint(_StubContext(), libraries=["MyLibrary"])

    error = await _error_of(endpoint.import_library(ImportLibraryParams(name="OtherLibrary")))

    assert error.code == JsonRpcErrorCode.INVALID_PARAMS
    assert error.message == "Library 'OtherLibrary' is not available."


async def test_import_without_a_name_and_without_a_default_library_is_answered_with_invalid_params() -> None:
    endpoint = await _initialized_endpoint(_StubContext())

    error = await _error_of(endpoint.import_library(ImportLibraryParams(name="")))

    assert error.code == JsonRpcErrorCode.INVALID_PARAMS
    assert "name cannot be empty" in error.message


async def test_log_level_is_info_if_the_client_reports_none() -> None:
    endpoint = await _initialized_endpoint(_StubContext())

    assert endpoint.log_level == "INFO"


async def test_log_level_comes_from_initialize_and_from_the_notification() -> None:
    endpoint = RobotServerEndpoint(remote_context=cast(RobotRemoteContext, _StubContext()))

    await endpoint.initialize(InitializeParams(log_level="DEBUG"))
    assert endpoint.log_level == "DEBUG"

    await endpoint.set_log_level(SetLogLevelParams(log_level="TRACE"))
    assert endpoint.log_level == "TRACE"
