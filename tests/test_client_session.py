"""Unit tests for the JsonRpcRemote client's session handling, against an in-process fake server
and fakes for the session's event loop."""

import asyncio
import contextlib
import gc
import logging
import re
import threading
import time
import warnings
import weakref
from collections.abc import Generator, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fake_server import NEVER_ANSWER, FakeServer, wait_until

from jsonrpcpeer import JsonRpcPeer
from JsonRpcRemote import JsonRpcRemote, _ClientEndpoint, _finalize_session, _Session, _SessionResources
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


# --- a failed start releases its resources ----------------------------------------


def test_failed_handshake_closes_the_connection(server: FakeServer, remote: JsonRpcRemote) -> None:
    remote._stop_session()
    server.script(IMPORT_LIBRARY_REQUEST, RuntimeError("library not allowed"))

    with pytest.raises(Exception, match="library not allowed"):
        _call(remote, "rejected")
    assert server.connections[-1].closed.wait(2), "the client did not close the rejected connection"


def test_failed_handshake_closes_the_connection_before_it_is_reported(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    server.script(IMPORT_LIBRARY_REQUEST, RuntimeError("library not allowed"))
    session = _Session(server.uri, "FakeLib", None, None, 5)
    closed_when_reported: list[bool] = []
    report = session.initialized.set

    def check_and_report() -> None:
        # Setting `initialized` is what hands the failure to the caller.
        peer = session._res.peer
        closed_when_reported.append(peer is not None and peer.writer.is_closing())
        report()

    monkeypatch.setattr(session.initialized, "set", check_and_report)
    session.start()

    assert session.initialized.wait(5)
    assert session.start_error is not None
    assert closed_when_reported == [True]


# --- a call never waits on an ended session --------------------------------------


@pytest.fixture
def closed_uri(server: FakeServer) -> str:
    """A URI that nothing listens on: the fake server's, after it stopped."""
    server.stop()
    return server.uri


async def _noop() -> None:
    pass


@contextlib.contextmanager
def _no_coroutine_left_unawaited() -> Generator[None, None, None]:
    gc.collect()  # so that only coroutines created inside the block are counted
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield
        gc.collect()
    assert not [warning for warning in caught if "was never awaited" in str(warning.message)]


def test_submit_to_a_session_that_has_not_started_fails(closed_uri: str) -> None:
    session = _Session(closed_uri, "FakeLib", None, None, 5)

    with _no_coroutine_left_unawaited(), pytest.raises(ConnectionError, match=r"is closed$"):
        session.submit(_noop())


def test_submit_to_a_session_that_has_ended_fails(closed_uri: str) -> None:
    session = _Session(closed_uri, "FakeLib", None, None, 5)
    session.start()
    assert session.ended.wait(5)

    with _no_coroutine_left_unawaited(), pytest.raises(ConnectionError, match=r"is closed$"):
        session.submit(_noop())


def test_call_stranded_by_the_end_of_the_session_fails(closed_uri: str) -> None:
    session = _Session(closed_uri, "FakeLib", None, None, 5)
    # A loop that never runs the call, as when the worker stops right after the call was handed over.
    idle_loop = asyncio.new_event_loop()
    session._res.loop = idle_loop
    call = _noop()
    try:
        future = session.submit(call)
        session.start()  # the worker fails to connect and ends

        assert session.ended.wait(5)
        assert isinstance(future.exception(timeout=1), ConnectionError)
    finally:
        call.close()
        idle_loop.close()


# --- a lost connection fails every later call of its session ---------------------


def _lost(server: FakeServer) -> str:
    """The pattern of the error for a call on a session whose connection ``server`` closed."""
    return f"^Connection to '{re.escape(server.uri)}' was lost: the connection was closed by the server$"


def test_connection_closed_by_the_server_is_a_loss(server: FakeServer, remote: JsonRpcRemote) -> None:
    session = _session(remote)
    server.close_connections()

    wait_until(lambda: session.lost)
    assert session.loss_cause() == "the connection was closed by the server"


def test_reset_connection_is_a_loss_caused_by_the_reset(server: FakeServer, remote: JsonRpcRemote) -> None:
    session = _session(remote)
    server.close_connections(reset=True)

    wait_until(lambda: session.lost)
    assert session.loss_cause().startswith("ConnectionResetError: ")


def test_session_stopped_by_the_client_is_not_a_loss(remote: JsonRpcRemote) -> None:
    session = _session(remote)
    session.stop()

    assert session.ended.wait(5)
    assert not session.lost


def test_the_peer_of_an_ended_session_is_freed(remote: JsonRpcRemote) -> None:
    peer_ref = weakref.ref(_session(remote)._res.peer)

    remote._stop_session()  # as at the end of the session's rpc_scope; the client drops the session
    gc.collect()

    assert peer_ref() is None


def test_calls_after_a_loss_fail_without_connecting_again(server: FakeServer, remote: JsonRpcRemote) -> None:
    session = _session(remote)
    server.close_connections()
    wait_until(lambda: session.lost)
    connections = len(server.connections)

    for message in ("first", "second"):
        with pytest.raises(ConnectionError, match=_lost(server)):
            _call(remote, message)
    assert len(server.connections) == connections


def test_call_after_the_lost_session_ended_connects_again(server: FakeServer, remote: JsonRpcRemote) -> None:
    session = _session(remote)
    server.close_connections()
    wait_until(lambda: session.lost)
    remote._stop_session()  # as at the end of the session's rpc_scope
    connections = len(server.connections)

    assert _call(remote, "again") == "echo: again"
    assert len(server.connections) == connections + 1


async def test_keyword_running_when_the_connection_is_lost_fails_and_is_not_sent_again(
    server: FakeServer, remote: JsonRpcRemote
) -> None:
    server.script(RUN_KEYWORD_REQUEST, NEVER_ANSWER)
    call = asyncio.ensure_future(remote.run_keyword("Echo", ["pending"], {}))
    await asyncio.to_thread(wait_until, lambda: RUN_KEYWORD_REQUEST in server.requests)

    server.close_connections()

    running = "while running keyword 'Echo': the connection was closed by the server"
    with pytest.raises(ConnectionError, match=f"^Connection to '{re.escape(server.uri)}' was lost {running}$"):
        await call
    assert server.requests.count(RUN_KEYWORD_REQUEST) == 1


async def test_cancelled_keyword_on_a_healthy_session_is_cancelled(server: FakeServer, remote: JsonRpcRemote) -> None:
    server.script(RUN_KEYWORD_REQUEST, NEVER_ANSWER)
    call = asyncio.ensure_future(remote.run_keyword("Echo", ["pending"], {}))
    await asyncio.to_thread(wait_until, lambda: RUN_KEYWORD_REQUEST in server.requests)

    call.cancel()  # as Robot Framework does when the keyword times out

    with pytest.raises(asyncio.CancelledError):
        await call
    assert not _session(remote).lost


# --- the worker thread does not print session errors -----------------------------


def test_failed_start_is_not_an_unhandled_thread_exception(
    closed_uri: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    unhandled: list[threading.ExceptHookArgs] = []
    monkeypatch.setattr(threading, "excepthook", unhandled.append)
    caplog.set_level(logging.DEBUG, logger="JsonRpcRemote")
    session = _Session(closed_uri, "FakeLib", None, None, 5)

    # The session's worker body, in a thread the test can join: the session drops its own
    # reference to the thread when the worker ends.
    worker = threading.Thread(target=session._run)
    worker.start()
    worker.join(5)

    assert isinstance(session.start_error, ConnectionRefusedError)
    assert unhandled == []
    logged = [
        record.exc_info[1]
        for record in caplog.records
        if record.name == "JsonRpcRemote" and record.levelno == logging.DEBUG and record.exc_info
    ]
    assert logged == [session.start_error]


# --- ending a session never raises -----------------------------------------------


@contextlib.contextmanager
def _unresponsive_worker() -> Generator[tuple[asyncio.AbstractEventLoop, threading.Thread], None, None]:
    """A worker thread whose event loop is blocked, so it does not process scheduled work."""
    loop = asyncio.new_event_loop()
    release = threading.Event()
    worker = threading.Thread(target=loop.run_forever, daemon=True)
    worker.start()
    loop.call_soon_threadsafe(release.wait)
    try:
        yield loop, worker
    finally:
        release.set()
        # Let the loop run what was scheduled meanwhile, so that no coroutine is left unawaited.
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop).result(5)
        loop.call_soon_threadsafe(loop.stop)
        worker.join(5)
        loop.close()


def _resources(loop: asyncio.AbstractEventLoop, thread: threading.Thread | None = None) -> _SessionResources:
    """The resources of a started session, with a fake peer."""
    resources = _SessionResources()
    resources.loop = loop
    resources.peer = MagicMock(spec=JsonRpcPeer)
    resources.endpoint = _ClientEndpoint()
    resources.thread = thread
    return resources


def test_ending_a_session_whose_worker_does_not_respond_returns_in_bounded_time() -> None:
    with _unresponsive_worker() as (loop, worker):
        resources = _resources(loop, worker)

        started = time.monotonic()
        _finalize_session(resources, 0.5)

        assert time.monotonic() - started < 2
    assert (resources.loop, resources.peer, resources.thread, resources.endpoint) == (None, None, None, None)


def test_ending_a_session_whose_event_loop_is_closed_does_not_raise() -> None:
    loop = asyncio.new_event_loop()
    loop.close()
    resources = _resources(loop)

    with _no_coroutine_left_unawaited():
        _finalize_session(resources, 0.5)

    assert (resources.loop, resources.peer) == (None, None)


def test_ending_a_session_without_a_peer_kills_the_recorded_server_process() -> None:
    resources = _SessionResources()
    process = MagicMock(returncode=None)
    resources.process = process

    _finalize_session(resources, 0.5)

    process.kill.assert_called_once_with()
    assert resources.process is None
