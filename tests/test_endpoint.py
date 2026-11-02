"""Unit tests for the server endpoint's handlers: the lifecycle, errors, failed keywords and the client's log level.

A stub stands in for ``RobotRemoteContext`` so the handlers can be exercised without a
running Robot suite.
"""

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any, cast

import pytest

from jsonrpcpeer import JsonRpcErrorCode, JsonRpcResponseError
from robot_jsonrpcremote_protocol import (
    ExitParams,
    FinalizeLibraryParams,
    ImportLibraryParams,
    InitializedParams,
    InitializeParams,
    LibraryDefinition,
    RobotJsonRpcErrorCode,
    RunKeywordError,
    RunKeywordErrorMode,
    RunKeywordParams,
    SetLogLevelParams,
    ShutdownParams,
)
from robot_jsonrpcremote_server._endpoint import RobotServerEndpoint
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
