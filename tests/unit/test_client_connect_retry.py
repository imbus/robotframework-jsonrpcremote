"""Unit tests for the JsonRpcRemote client's connect retry, against an in-process fake server."""

import asyncio
import contextlib
import gc
import itertools
import logging
import re
import sys
import threading
import time
from collections.abc import Callable, Generator, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fake_server import NEVER_ANSWER, FakeServer, wait_until

from JsonRpcRemote import JsonRpcRemote, _definition_changes, _Session, _time_option
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    RUN_KEYWORD_REQUEST,
    KeywordDefinition,
    LibraryDefinition,
)


@pytest.fixture
def server() -> Iterator[FakeServer]:
    with FakeServer() as fake:
        yield fake


@pytest.fixture
def connect(server: FakeServer) -> Iterator[Callable[..., JsonRpcRemote]]:
    """Import the fake library with the given client options; the libraries are stopped after the test."""
    remotes: list[JsonRpcRemote] = []

    def connect(**options: Any) -> JsonRpcRemote:
        remote = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5, **options)
        remotes.append(remote)
        return remote

    try:
        yield connect
    finally:
        for remote in remotes:
            remote._stop_session()


def _call(remote: JsonRpcRemote, *args: Any) -> Any:
    """Run the fake library's ``Echo`` keyword the way Robot Framework calls it."""
    return asyncio.run(remote.run_keyword("Echo", list(args), {}))


def _session(remote: JsonRpcRemote) -> Any:
    """The client's current session (``None`` if it has none), a name-mangled private attribute."""
    return getattr(remote, "_JsonRpcRemote__session")


def _record_attempts(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the time.monotonic() of every connection attempt from now on."""
    attempts: list[float] = []
    connect = JsonRpcRemote._connect

    def record(remote: JsonRpcRemote) -> _Session:
        attempts.append(time.monotonic())
        return connect(remote)

    monkeypatch.setattr(JsonRpcRemote, "_connect", record)
    return attempts


@contextlib.contextmanager
def _listening_after(server: FakeServer, delay: float) -> Generator[None, None, None]:
    """Let the stopped ``server`` listen again ``delay`` seconds from now."""
    timer = threading.Timer(delay, server.start)
    timer.start()
    try:
        yield
    finally:
        timer.join()


def _robot_log(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    """The messages logged through Robot Framework's logger: outside a run, it uses Python's logging."""
    return [(record.levelno, record.getMessage()) for record in caplog.records if record.name == "RobotFramework"]


# --- options ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "seconds"),
    [(5, 5.0), (2.5, 2.5), ("2.5", 2.5), ("60s", 60.0), ("1 minute", 60.0), ("1min 30s", 90.0), ("0", 0.0)],
)
def test_time_options_accept_seconds_and_robot_time_strings(value: float | str, seconds: float) -> None:
    assert _time_option("rpc_timeout", value) == seconds


def test_options_given_as_robot_time_strings(server: FakeServer) -> None:
    remote = JsonRpcRemote(
        server.uri,
        "FakeLib",
        rpc_timeout="15s",
        rpc_connect_retry_timeout="1 minute",
        rpc_connect_retry_interval="2s",
    )
    try:
        assert (remote._timeout, remote._retry_timeout, remote._retry_interval) == (15.0, 60.0, 2.0)
    finally:
        remote._stop_session()


def test_connect_retry_is_disabled_by_default(server: FakeServer) -> None:
    remote = JsonRpcRemote(server.uri, "FakeLib")
    try:
        assert (remote._retry_timeout, remote._retry_interval) == (0.0, 1.0)
    finally:
        remote._stop_session()


@pytest.mark.parametrize("option", ["rpc_timeout", "rpc_connect_retry_timeout", "rpc_connect_retry_interval"])
@pytest.mark.parametrize("value", ["soon", -1, "-1s"])
def test_invalid_option_value_fails_the_import_before_connecting(
    option: str, value: float | str, server: FakeServer
) -> None:
    options: dict[str, Any] = {option: value}
    with pytest.raises(ValueError, match=f"^Invalid value for {option}: "):
        JsonRpcRemote(server.uri, "FakeLib", **options)
    assert server.connections == []


def test_interval_of_zero_with_connect_retry_fails_the_import(server: FakeServer) -> None:
    with pytest.raises(ValueError, match=r"^Invalid value for rpc_connect_retry_interval: "):
        JsonRpcRemote(server.uri, "FakeLib", rpc_connect_retry_timeout="10s", rpc_connect_retry_interval=0)
    assert server.connections == []


def test_interval_of_zero_without_connect_retry_is_accepted(server: FakeServer) -> None:
    remote = JsonRpcRemote(server.uri, "FakeLib", rpc_connect_retry_interval=0)
    remote._stop_session()


def test_rejected_options_leave_no_error_for_the_finalizer(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> None:
    unraisable: list[Any] = []
    monkeypatch.setattr(sys, "unraisablehook", unraisable.append)

    with pytest.raises(ValueError, match=r"^Invalid value for rpc_timeout: ") as rejected:
        JsonRpcRemote(server.uri, "FakeLib", rpc_timeout="soon")
    # The traceback holds the half-initialized library; release it, so that its __del__ runs.
    del rejected
    gc.collect()

    assert unraisable == []


def test_connect_retry_options_are_not_forwarded(server: FakeServer) -> None:
    remote = JsonRpcRemote(
        server.uri,
        "FakeLib",
        rpc_connect_retry_timeout="10s",
        rpc_connect_retry_interval="0.5s",
        greeting="hello",
    )
    try:
        imports = [params for method, params in zip(server.requests, server.params) if method == IMPORT_LIBRARY_REQUEST]
        assert imports[-1]["kw_args"] == {"greeting": "hello"}
    finally:
        remote._stop_session()


# --- retry window and giving up --------------------------------------------------


def test_import_waits_for_a_server_that_comes_up_within_the_window(
    server: FakeServer, connect: Callable[..., JsonRpcRemote]
) -> None:
    server.stop()

    # How many attempts that takes depends on the platform: on Windows, an attempt to connect to a
    # port that nobody listens on stays pending for a while, so it can succeed once the server is up.
    with _listening_after(server, 1.0):
        remote = connect(rpc_connect_retry_timeout=10, rpc_connect_retry_interval=0.1)

    assert remote.get_keyword_names() == ["Echo"]
    assert _call(remote, "up") == "echo: up"


def test_failed_attempts_are_repeated_every_interval(
    server: FakeServer, connect: Callable[..., JsonRpcRemote], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = connect(rpc_connect_retry_timeout=10, rpc_connect_retry_interval=0.2)
    remote._stop_session()  # as at the end of the session's rpc_scope
    server.script(IMPORT_LIBRARY_REQUEST, RuntimeError("not ready"), RuntimeError("not ready"))
    attempts = _record_attempts(monkeypatch)

    assert _call(remote, "up") == "echo: up"

    assert len(attempts) == 3
    # Spaced by the interval (with some slack for coarse clocks).
    assert all(later - earlier >= 0.15 for earlier, later in itertools.pairwise(attempts))


def test_connect_retry_gives_up_once_per_outage(
    server: FakeServer, connect: Callable[..., JsonRpcRemote], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = connect(rpc_connect_retry_timeout=1, rpc_connect_retry_interval=0.1)
    remote._stop_session()  # as at the end of the session's rpc_scope
    server.stop()
    attempts = _record_attempts(monkeypatch)
    gave_up = (
        rf"^Could not connect to '{re.escape(server.uri)}' within 1 second \((\d+) attempts?\): ConnectionRefusedError"
    )

    started = time.monotonic()
    with pytest.raises(ConnectionError, match=gave_up) as error:
        _call(remote, "down")
    assert time.monotonic() - started >= 1.0
    match = re.match(gave_up, str(error.value))
    assert match is not None
    assert int(match.group(1)) == len(attempts)
    assert isinstance(error.value.__cause__, ConnectionRefusedError)

    # The window is spent: until a connection succeeds, each call tries once and does not wait.
    attempts.clear()
    with pytest.raises(ConnectionRefusedError):
        _call(remote, "still down")
    assert len(attempts) == 1

    server.start()
    assert _call(remote, "back") == "echo: back"

    # The connection succeeded, so the next outage gets the full window again.
    remote._stop_session()
    server.stop()
    started = time.monotonic()
    with pytest.raises(ConnectionError, match=gave_up):
        _call(remote, "down again")
    assert time.monotonic() - started >= 1.0


def test_connection_that_needed_several_attempts_is_logged_as_info(
    server: FakeServer,
    connect: Callable[..., JsonRpcRemote],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    remote = connect(rpc_connect_retry_timeout=10, rpc_connect_retry_interval=0.1)
    remote._stop_session()  # as at the end of the session's rpc_scope
    server.script(IMPORT_LIBRARY_REQUEST, RuntimeError("not ready"), RuntimeError("not ready"))
    attempts = _record_attempts(monkeypatch)
    caplog.set_level(logging.INFO, logger="RobotFramework")

    assert _call(remote, "up") == "echo: up"

    assert len(attempts) == 3
    connected = rf"Connected to '{re.escape(server.uri)}' after \d+\.\ds \(3 attempts\)\."
    [(level, message)] = _robot_log(caplog)
    assert level == logging.INFO
    assert re.fullmatch(connected, message)


def test_connection_at_the_first_attempt_is_not_logged(
    connect: Callable[..., JsonRpcRemote], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="RobotFramework")

    connect(rpc_connect_retry_timeout=10)

    assert _robot_log(caplog) == []


# --- reconnect after a lost connection -------------------------------------------


def test_call_after_a_lost_connection_reconnects_and_logs_a_warning(
    server: FakeServer,
    connect: Callable[..., JsonRpcRemote],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    remote = connect(rpc_connect_retry_timeout=10, rpc_connect_retry_interval=0.1)
    lost = _session(remote)
    server.stop()  # closes the connection, like a server that restarts
    wait_until(lambda: lost.lost)
    attempts = _record_attempts(monkeypatch)
    caplog.set_level(logging.INFO, logger="RobotFramework")

    with _listening_after(server, 0.5):
        assert _call(remote, "again") == "echo: again"

    assert _session(remote) is not lost
    assert server.requests.count(IMPORT_LIBRARY_REQUEST) == 2
    # One attempt or several, depending on the platform (see the test of the import above).
    count = f"{len(attempts)} attempt" if len(attempts) == 1 else f"{len(attempts)} attempts"
    reconnected = (
        rf"Connection to '{re.escape(server.uri)}' was lost: the connection was closed by the server\. "
        rf"Reconnected after (\d+\.\d)s \({count}\); "
        r"the remote library was imported again, so its server-side state was reset\."
    )
    [(level, message)] = _robot_log(caplog)
    assert level == logging.WARNING
    match = re.fullmatch(reconnected, message)
    assert match is not None, message
    assert float(match.group(1)) >= 0.4, "the time until it reconnected includes the wait for the server"


def test_reconnect_warning_counts_the_failed_attempts(
    server: FakeServer, connect: Callable[..., JsonRpcRemote], caplog: pytest.LogCaptureFixture
) -> None:
    remote = connect(rpc_connect_retry_timeout=10, rpc_connect_retry_interval=0.1)
    lost = _session(remote)
    server.close_connections()
    wait_until(lambda: lost.lost)
    server.script(IMPORT_LIBRARY_REQUEST, RuntimeError("not ready"))
    caplog.set_level(logging.WARNING, logger="RobotFramework")

    assert _call(remote, "again") == "echo: again"

    [(_, message)] = _robot_log(caplog)
    assert " (2 attempts); " in message


async def test_keyword_running_at_the_loss_is_not_sent_again_and_the_next_call_reconnects(
    server: FakeServer, connect: Callable[..., JsonRpcRemote]
) -> None:
    remote = connect(rpc_connect_retry_timeout=10, rpc_connect_retry_interval=0.1)
    server.script(RUN_KEYWORD_REQUEST, NEVER_ANSWER)
    call = asyncio.ensure_future(remote.run_keyword("Echo", ["pending"], {}))
    await asyncio.to_thread(wait_until, lambda: RUN_KEYWORD_REQUEST in server.requests)

    server.close_connections()

    with pytest.raises(ConnectionError, match="was lost while running keyword 'Echo'"):
        await call
    assert await remote.run_keyword("Echo", ["next"], {}) == "echo: next"
    sent = [params["args"] for method, params in zip(server.requests, server.params) if method == RUN_KEYWORD_REQUEST]
    assert sent == [["pending"], ["next"]]


def test_session_after_the_scope_of_a_lost_session_ended_is_no_reconnect(
    server: FakeServer, connect: Callable[..., JsonRpcRemote], caplog: pytest.LogCaptureFixture
) -> None:
    remote = connect(rpc_connect_retry_timeout=0.5, rpc_connect_retry_interval=0.1)
    lost = _session(remote)
    server.stop()
    wait_until(lambda: lost.lost)
    with pytest.raises(ConnectionError, match=r"^Could not connect"):
        _call(remote, "down")
    caplog.set_level(logging.INFO, logger="RobotFramework")

    remote._end_suite(MagicMock(), MagicMock())  # the session's rpc_scope (SUITE) ends
    server.keywords.append("Other")  # not checked: Robot Framework imports the library again for a new scope
    server.start()

    assert _call(remote, "next suite") == "echo: next suite"
    assert [level for level, _ in _robot_log(caplog)] == [logging.INFO]


# --- a changed library definition after a reconnect -------------------------------


def test_changed_library_definition_after_a_reconnect_fails_until_the_session_ends(
    server: FakeServer, connect: Callable[..., JsonRpcRemote]
) -> None:
    remote = connect(rpc_connect_retry_timeout=10, rpc_connect_retry_interval=0.1)
    lost = _session(remote)
    server.keywords.append("Other")  # the server comes back with another version of the library
    server.close_connections()
    wait_until(lambda: lost.lost)
    changed = (
        rf"^Reconnected to '{re.escape(server.uri)}', but the library definition changed since the library was "
        r"imported \(keywords added: Other\); the library cannot be used until its session ends according to "
        r"rpc_scope\.$"
    )

    with pytest.raises(ConnectionError, match=changed):
        _call(remote, "first")
    assert server.connections[-1].closed.wait(5), "the client did not close the new session"
    connections = len(server.connections)

    with pytest.raises(ConnectionError, match=changed):
        _call(remote, "second")
    assert len(server.connections) == connections

    remote._end_suite(MagicMock(), MagicMock())  # the session's rpc_scope (SUITE) ends
    assert _call(remote, "next suite") == "echo: next suite"
    assert len(server.connections) == connections + 1


_ECHO = KeywordDefinition(name="Echo", args=[])
_OTHER = KeywordDefinition(name="Other", args=[])


@pytest.mark.parametrize(
    ("current", "changes"),
    [
        (LibraryDefinition(name="Lib", keywords=[_ECHO, _OTHER]), ""),
        # The server names each imported instance differently.
        (LibraryDefinition(name="Lib_2", keywords=[_ECHO, _OTHER]), ""),
        (
            LibraryDefinition(name="Lib", keywords=[_ECHO, _OTHER], version="2", source="/new/Lib.py"),
            "library attributes changed: version, source",
        ),
        (
            LibraryDefinition(name="Lib", keywords=[KeywordDefinition(name="Echo", args=[], doc="New.")]),
            "keywords removed: Other; keywords changed: Echo",
        ),
        (LibraryDefinition(name="Lib", keywords=[_OTHER, _ECHO]), "the order of the keywords changed"),
    ],
)
def test_definition_changes_name_what_changed(current: LibraryDefinition, changes: str) -> None:
    registered = LibraryDefinition(name="Lib", keywords=[_ECHO, _OTHER])

    assert _definition_changes(registered, current) == changes
