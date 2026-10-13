"""Unit tests for the JsonRpcRemote client's reconnect logic (end-to-end behavior against a
restarted server is covered by tests/robot/reconnect.robot and stdio_reconnect.robot)."""

import asyncio
import concurrent.futures
import os
import sys
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from robot.api import logger as robot_logger

from JsonRpcRemote import JsonRpcRemote, _Session, _time_option
from robot_jsonrpcremote_protocol import KeywordDefinition, LibraryDefinition, RunKeywordResult

_ROBOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "robot"))


class _FakeSession:
    """Stands in for _Session: only what JsonRpcRemote looks at."""

    def __init__(self, keywords: list[str], lost: bool = False) -> None:
        self.connection_lost = lost
        self.library_definition = LibraryDefinition(
            name="Lib", keywords=[KeywordDefinition(name=name, args=[]) for name in keywords]
        )
        self.client_endpoint = SimpleNamespace(callback_loop=None)
        # What submit() hands back for a keyword call.
        self.call_outcome: "concurrent.futures.Future[Any]" = concurrent.futures.Future()

    def describe_disconnect(self) -> str:
        return "the connection was closed by the server"

    def stop(self) -> None:  # called by JsonRpcRemote.__del__
        pass

    async def run_keyword(self, name: str, args: list[Any], named: dict[str, Any]) -> RunKeywordResult:
        raise AssertionError("not expected to run; submit() is faked")

    def submit(self, coro: Any) -> "concurrent.futures.Future[Any]":
        coro.close()
        return self.call_outcome


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(robot_logger, "warn", lambda msg, *args, **kwargs: messages.append(msg))
    return messages


def _make_client(monkeypatch: pytest.MonkeyPatch, **options: Any) -> JsonRpcRemote:
    """A client whose initial connection is skipped; sessions are injected by the tests."""
    with monkeypatch.context() as patched:
        patched.setattr(JsonRpcRemote, "_start_session", lambda self: None)
        return JsonRpcRemote("tcp://127.0.0.1:1", "Lib", **options)


def _set_session(remote: JsonRpcRemote, session: _FakeSession | None) -> None:
    remote._JsonRpcRemote__session = cast(_Session, session)  # type: ignore[attr-defined]


def _get_session(remote: JsonRpcRemote) -> Any:
    return remote._JsonRpcRemote__session  # type: ignore[attr-defined]


def _start(remote: JsonRpcRemote) -> Any:
    return remote._start_session()


def _scripted_connect(remote: JsonRpcRemote, results: list[Any]) -> list[int]:
    """Make _connect return/raise the given results in order; returns a call counter."""
    calls = [0]

    def connect() -> Any:
        calls[0] += 1
        outcome = results.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    remote._connect = connect  # type: ignore[method-assign]
    return calls


# --- options ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0.0), (2, 2.0), (1.5, 1.5), ("60s", 60.0), ("1 minute", 60.0), ("2.5", 2.5), (timedelta(seconds=3), 3.0)],
)
def test_time_option_accepts_numbers_and_robot_time_strings(value: Any, expected: float) -> None:
    assert _time_option("reconnect_timeout", value) == expected


@pytest.mark.parametrize("value", ["soon", "-1s", -1])
def test_time_option_rejects_invalid_values(value: Any) -> None:
    with pytest.raises(ValueError, match="reconnect_timeout"):
        _time_option("reconnect_timeout", value)


def test_reconnect_options_are_not_forwarded_to_the_remote_library(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _make_client(monkeypatch, reconnect_timeout="60s", reconnect_interval="2s", greeting="hi")
    assert remote._reconnect_timeout == 60.0
    assert remote._reconnect_interval == 2.0
    assert remote._library_kw_args == {"greeting": "hi"}


def test_reconnect_interval_must_be_positive_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="reconnect_interval"):
        _make_client(monkeypatch, reconnect_timeout=5, reconnect_interval=0)


# --- lost connection handling ---------------------------------------------------


def test_lost_connection_without_reconnect_fails_clearly_every_time(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _make_client(monkeypatch)
    _set_session(remote, _FakeSession(["Echo"], lost=True))
    calls = _scripted_connect(remote, [])

    for _ in range(2):
        with pytest.raises(ConnectionError, match=r"closed by the server.*reconnect is disabled"):
            _start(remote)

    assert calls[0] == 0


def test_reconnect_retries_until_the_server_is_back(monkeypatch: pytest.MonkeyPatch, warnings: list[str]) -> None:
    remote = _make_client(monkeypatch, reconnect_timeout=10, reconnect_interval=0.01)
    _set_session(remote, _FakeSession(["Echo"], lost=True))
    fresh = _FakeSession(["Echo"])
    calls = _scripted_connect(remote, [ConnectionRefusedError(), ConnectionRefusedError(), fresh])

    assert _start(remote) is fresh
    assert _get_session(remote) is fresh
    assert calls[0] == 3
    assert len(warnings) == 1
    assert "was lost (the connection was closed by the server). Reconnected" in warnings[0]
    assert "3 attempt(s)" in warnings[0]


def test_reconnect_gives_up_after_timeout_and_next_call_connects_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _make_client(monkeypatch, reconnect_timeout=0.05, reconnect_interval=0.01)
    _set_session(remote, _FakeSession(["Echo"], lost=True))
    _scripted_connect(remote, [ConnectionRefusedError("refused")] * 1000)

    with pytest.raises(ConnectionError, match=r"could not be re-established within 0\.05s .*refused"):
        _start(remote)
    assert _get_session(remote) is None

    fresh = _FakeSession(["Echo"])
    calls = _scripted_connect(remote, [fresh])
    assert _start(remote) is fresh
    assert calls[0] == 1


def test_changed_keywords_after_reconnect_are_reported(monkeypatch: pytest.MonkeyPatch, warnings: list[str]) -> None:
    remote = _make_client(monkeypatch, reconnect_timeout=5, reconnect_interval=0.01)
    _set_session(remote, _FakeSession(["Echo", "Old"], lost=True))
    _scripted_connect(remote, [_FakeSession(["Echo", "New"])])

    _start(remote)

    assert any("added: New; removed: Old" in w for w in warnings)


def test_healthy_session_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _make_client(monkeypatch, reconnect_timeout=5)
    session = _FakeSession(["Echo"])
    _set_session(remote, session)
    calls = _scripted_connect(remote, [])

    assert _start(remote) is session
    assert calls[0] == 0


# --- keyword calls interrupted by a lost connection ------------------------------


async def test_running_call_that_loses_the_connection_fails_with_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = _make_client(monkeypatch)
    session = _FakeSession(["Echo"])
    session.call_outcome.set_exception(ConnectionResetError("reset"))
    _set_session(remote, session)

    with pytest.raises(ConnectionError, match=r"while running keyword 'Echo'.*not retried"):
        await remote.run_keyword("Echo", [], {})


async def test_call_cancelled_by_a_dying_session_fails_with_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _make_client(monkeypatch)
    session = _FakeSession(["Echo"])
    session.call_outcome.cancel()
    session.connection_lost = True
    _set_session(remote, session)

    with monkeypatch.context() as patched:
        # Hand the call its session even though it is already marked lost.
        patched.setattr(JsonRpcRemote, "_session", property(lambda self: session))
        with pytest.raises(ConnectionError, match="while running keyword 'Echo'"):
            await remote.run_keyword("Echo", [], {})


async def test_cancellation_of_a_healthy_call_is_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _make_client(monkeypatch)
    session = _FakeSession(["Echo"])
    session.call_outcome.cancel()
    _set_session(remote, session)

    with pytest.raises(asyncio.CancelledError):
        await remote.run_keyword("Echo", [], {})


# --- _Session -------------------------------------------------------------------


def test_session_is_not_lost_before_the_handshake() -> None:
    assert not _Session("tcp://127.0.0.1:1", None, None, None).connection_lost


def test_session_without_running_peer_is_lost_unless_closed_by_client() -> None:
    session = _Session("tcp://127.0.0.1:1", None, None, None)
    session.library_token = "token"  # handshake completed, peer gone
    assert session.connection_lost

    session.stop()
    assert not session.connection_lost


def test_submit_to_an_ended_session_raises_connection_error() -> None:
    session = _Session("tcp://127.0.0.1:1", None, None, None)

    async def noop() -> None:
        pass

    with pytest.raises(ConnectionError, match="is closed"):
        session.submit(noop())


def test_call_never_run_by_the_loop_fails_when_the_session_ends() -> None:
    # A call submitted just before the loop shut down must not hang forever.
    session = _Session("tcp://127.0.0.1:1", None, None, None, timeout=5)
    idle_loop = asyncio.new_event_loop()  # never runs, so the call is never started
    session._res.loop = idle_loop

    async def noop() -> None:
        pass

    call = noop()
    try:
        future = session.submit(call)
        session._run()  # the connection is refused, so the worker ends right away

        assert session.ended.is_set()
        with pytest.raises(ConnectionError, match="is closed"):
            future.result(timeout=1)
    finally:
        call.close()
        idle_loop.close()


@pytest.mark.skipif(sys.platform == "win32", reason="the stdio server transport is POSIX-only")
def test_failed_handshake_closes_the_connection_and_reaps_the_stdio_server() -> None:
    command = f"{sys.executable} -m robot_jsonrpcremote_server --stdio --pythonpath {_ROBOT_DIR} StdioEchoLib"
    session = _Session(f"stdio:{command}", "NotAllowedLib", (), None, 20.0)
    session.start()

    assert session.initialized.wait(20)
    assert session.last_error is not None
    assert session.ended.wait(20)
    assert session.process_returncode is not None
