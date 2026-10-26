"""Unit tests for the JsonRpcRemote client's session handling, against an in-process fake server."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fake_server import NEVER_ANSWER, FakeServer

from JsonRpcRemote import JsonRpcRemote
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    RUN_KEYWORD_REQUEST,
    RunKeywordError,
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


def _call(remote: JsonRpcRemote, *args: Any) -> Any:
    """Run the fake library's ``Echo`` keyword the way Robot Framework calls it."""
    return asyncio.run(remote.run_keyword("Echo", list(args), {}))


def _session(remote: JsonRpcRemote) -> Any:
    """The client's current session (``None`` if it has none), a name-mangled private attribute."""
    return getattr(remote, "_JsonRpcRemote__session")


def test_fake_server_serves_a_keyword(remote: JsonRpcRemote) -> None:
    assert remote.get_keyword_names() == ["Echo"]
    assert _call(remote, "hello") == "echo: hello"


# --- a failed keyword call affects only that call --------------------------------


def test_keyword_answered_with_rpc_error_does_not_poison_the_session(server: FakeServer, remote: JsonRpcRemote) -> None:
    server.script(RUN_KEYWORD_REQUEST, RuntimeError("rpc failure"))

    with pytest.raises(Exception, match="rpc failure"):
        _call(remote, "first")
    assert _call(remote, "second") == "echo: second"
    assert _session(remote).start_error is None


def test_failed_remote_keyword_does_not_poison_the_session(server: FakeServer, remote: JsonRpcRemote) -> None:
    server.script(RUN_KEYWORD_REQUEST, RunKeywordResult(error=RunKeywordError(message="keyword failed")))

    with pytest.raises(RuntimeError, match="keyword failed"):
        _call(remote, "first")
    assert _call(remote, "second") == "echo: second"
    assert _session(remote).start_error is None


# --- only a session that started is kept -----------------------------------------
# Each test ends the healthy session from the fixture first, as the end of a test or
# suite does, so the next call has to start a new one.


def test_unreachable_server_at_session_start_is_not_kept(server: FakeServer, remote: JsonRpcRemote) -> None:
    remote._stop_session()
    server.stop()

    with pytest.raises(ConnectionRefusedError):
        _call(remote, "while down")
    assert _session(remote) is None

    server.start()
    assert _call(remote, "back") == "echo: back"


def test_rejected_handshake_is_not_kept(server: FakeServer, remote: JsonRpcRemote) -> None:
    remote._stop_session()
    server.script(IMPORT_LIBRARY_REQUEST, RuntimeError("library not allowed"))

    with pytest.raises(Exception, match="library not allowed"):
        _call(remote, "rejected")
    assert _session(remote) is None
    connections = len(server.connections)

    assert _call(remote, "accepted") == "echo: accepted"
    assert len(server.connections) == connections + 1


def test_timed_out_start_is_stopped(server: FakeServer) -> None:
    remote = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=1)
    try:
        remote._stop_session()
        server.script(INITIALIZE_REQUEST, NEVER_ANSWER)

        with pytest.raises(TimeoutError):
            _call(remote, "never answered")
        assert _session(remote) is None
        timed_out = server.connections[-1]
        assert timed_out.closed.wait(5), "the client did not close the timed-out connection"

        assert _call(remote, "answered") == "echo: answered"
        assert server.connections[-1] is not timed_out
    finally:
        remote._stop_session()
