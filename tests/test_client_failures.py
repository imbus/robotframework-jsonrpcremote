"""Unit tests for how the JsonRpcRemote client reports a failed remote keyword, against an in-process fake server.

The tests look at the client's exception the way Robot Framework's status reporter does.
"""

import asyncio
from collections.abc import Iterator

import pytest
from fake_server import FakeServer
from robot.errors import HandlerExecutionFailed, RemoteError
from robot.utils import ErrorDetails

from JsonRpcRemote import JsonRpcRemote
from robot_jsonrpcremote_protocol import RUN_KEYWORD_REQUEST, RunKeywordError, RunKeywordErrorMode, RunKeywordResult


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


def _failure(server: FakeServer, remote: JsonRpcRemote, error: RunKeywordError) -> RemoteError:
    """The client's exception for a keyword call that the server answers with ``error``."""
    server.script(RUN_KEYWORD_REQUEST, RunKeywordResult(error=error))
    with pytest.raises(RemoteError) as raised:
        asyncio.run(remote.run_keyword("Echo", ["value"], {}))
    return raised.value


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
