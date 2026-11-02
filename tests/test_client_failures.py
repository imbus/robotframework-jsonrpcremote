"""Unit tests for how the JsonRpcRemote client reports failed remote keywords and error responses,
against an in-process fake server.

The tests look at the client's exception the way Robot Framework's status reporter does.
"""

import asyncio
from collections.abc import Iterator

import pytest
from fake_server import FakeServer
from robot.errors import HandlerExecutionFailed, RemoteError
from robot.utils import ErrorDetails

from jsonrpcpeer import JsonRpcResponseError
from JsonRpcRemote import JsonRpcRemote
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    RUN_KEYWORD_REQUEST,
    RunKeywordError,
    RunKeywordErrorMode,
    RunKeywordResult,
)


@pytest.fixture
def server() -> Iterator[FakeServer]:
    with FakeServer() as fake:
        yield fake


@pytest.fixture
def remote(server: FakeServer) -> Iterator[JsonRpcRemote]:
    client = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5)
    try:
        yield client
    finally:
        client._stop_session()


def _failure_of_call(server: FakeServer, remote: JsonRpcRemote, answer: object) -> RemoteError:
    """The client's exception for a keyword call that the server answers with ``answer``."""
    server.script(RUN_KEYWORD_REQUEST, answer)
    with pytest.raises(RemoteError) as raised:
        asyncio.run(remote.run_keyword("Echo", ["value"], {}))
    return raised.value


def _failure(server: FakeServer, remote: JsonRpcRemote, error: RunKeywordError) -> RemoteError:
    """The client's exception for a keyword call that the server answers with ``error``."""
    return _failure_of_call(server, remote, RunKeywordResult(error=error))


@pytest.mark.parametrize("message", ["ValueError: bad value", "boom"])
def test_keyword_call_fails_with_exactly_the_message_of_the_server(
    server: FakeServer, remote: JsonRpcRemote, message: str
) -> None:
    error = RunKeywordError(message=message, type="ValueError", traceback="the trace")

    assert ErrorDetails(_failure(server, remote, error)).message == message


def test_traceback_of_the_server_replaces_the_one_of_the_client_and_is_marked(
    server: FakeServer, remote: JsonRpcRemote
) -> None:
    error = RunKeywordError(message="boom", traceback="the trace")

    assert ErrorDetails(_failure(server, remote, error)).traceback == "[remote] the trace"


@pytest.mark.parametrize(
    ("mode", "skip", "fatal", "continuable"),
    [
        (RunKeywordErrorMode.SKIP, True, False, False),
        (RunKeywordErrorMode.FATAL, False, True, False),
        (RunKeywordErrorMode.CONTINUABLE, False, False, True),
    ],
)
def test_failure_mode_reaches_robot_framework(
    server: FakeServer, remote: JsonRpcRemote, mode: RunKeywordErrorMode, skip: bool, fatal: bool, continuable: bool
) -> None:
    error = RunKeywordError(message="boom", mode=mode)

    failure = HandlerExecutionFailed(ErrorDetails(_failure(server, remote, error)))

    assert (failure.skip, failure.exit, failure.continue_on_failure) == (skip, fatal, continuable)
    assert failure.message == "boom"


def test_failure_with_a_message_only_is_a_normal_failure(server: FakeServer, remote: JsonRpcRemote) -> None:
    details = ErrorDetails(_failure(server, remote, RunKeywordError(message="boom")))

    failure = HandlerExecutionFailed(details)

    assert failure.message == "boom"
    assert details.traceback == ""
    assert (failure.skip, failure.exit, failure.continue_on_failure) == (False, False, False)


def test_error_response_fails_the_keyword_call_with_exactly_its_message_as_a_normal_failure(
    server: FakeServer, remote: JsonRpcRemote
) -> None:
    message = "Keyword 'Gone' not found in library 'MyLibrary'."

    details = ErrorDetails(_failure_of_call(server, remote, JsonRpcResponseError(-32001, message)))

    failure = HandlerExecutionFailed(details)
    assert failure.message == message
    assert details.traceback == ""
    assert (failure.skip, failure.exit, failure.continue_on_failure) == (False, False, False)


@pytest.mark.parametrize(
    ("data", "traceback"), [("details", "[remote] details"), ({"line": 1}, "[remote] {'line': 1}")]
)
def test_data_of_an_error_response_is_marked_and_replaces_the_traceback_of_the_client(
    server: FakeServer, remote: JsonRpcRemote, data: object, traceback: str
) -> None:
    details = ErrorDetails(_failure_of_call(server, remote, JsonRpcResponseError(-32603, "boom", data)))

    assert details.message == "boom"
    assert details.traceback == traceback


def _failure_of_import(server: FakeServer, error: JsonRpcResponseError) -> RemoteError:
    """The client's exception for a library import that the server answers with ``error``."""
    server.script(IMPORT_LIBRARY_REQUEST, error)
    with pytest.raises(RemoteError) as raised:
        JsonRpcRemote(server.uri, "OtherLibrary", rpc_timeout=5)
    return raised.value


def test_error_response_fails_the_library_import_with_exactly_its_message(server: FakeServer) -> None:
    message = "Library 'OtherLibrary' is not available."

    details = ErrorDetails(_failure_of_import(server, JsonRpcResponseError(-32602, message)))

    assert details.message == message
    assert details.traceback == ""


def test_data_of_an_error_response_follows_the_message_at_a_library_import(server: FakeServer) -> None:
    details = ErrorDetails(_failure_of_import(server, JsonRpcResponseError(-32603, "boom", "details")))

    assert details.message == "boom"
    assert details.traceback == "[remote] details"


def test_error_response_to_the_import_of_a_later_session_fails_the_keyword_call(server: FakeServer) -> None:
    message = "Library 'OtherLibrary' is not available."
    remote = JsonRpcRemote(server.uri, "OtherLibrary", rpc_timeout=5, rpc_scope="TEST")
    remote._stop_session()  # as at the end of the session's rpc_scope
    server.script(IMPORT_LIBRARY_REQUEST, JsonRpcResponseError(-32602, message))

    with pytest.raises(RemoteError) as raised:
        asyncio.run(remote.run_keyword("Echo", ["value"], {}))

    details = ErrorDetails(raised.value)
    assert details.message == message
    assert details.traceback == ""


def test_error_response_is_named_as_the_last_error_when_connect_retry_gives_up(server: FakeServer) -> None:
    remote = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5, rpc_connect_retry_timeout=0.2)
    remote._stop_session()  # as at the end of the session's rpc_scope
    server.script(IMPORT_LIBRARY_REQUEST, *[JsonRpcResponseError(-32602, "refused")] * 5)

    with pytest.raises(
        ConnectionError, match=r"^Could not connect .*: JsonRpcResponseError: RPC Error -32602: refused$"
    ):
        asyncio.run(remote.run_keyword("Echo", ["value"], {}))
