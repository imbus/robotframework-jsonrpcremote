"""Unit tests for how the JsonRpcRemote client hands log messages from the server to Robot Framework."""

import asyncio
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fake_server import FakeServer, LogFirst

from JsonRpcRemote import JsonRpcRemote, SessionScope, _LogSink, _write_log
from robot_jsonrpcremote_protocol import FINALIZE_LIBRARY_REQUEST, IMPORT_LIBRARY_REQUEST


class _RecordingLogger:
    """Stands in for `robot.api.logger`; `write` has `console` only like Robot Framework 7.4 and later."""

    def __init__(self) -> None:
        self.writes: list[tuple[Any, ...]] = []
        self.console_messages: list[str] = []

    def write_with_console(self, msg: str, level: str = "INFO", html: bool = False, console: bool = False) -> None:
        self.writes.append((msg, level, html, console))

    def write_without_console(self, msg: str, level: str = "INFO", html: bool = False) -> None:
        self.writes.append((msg, level, html))

    def console(self, msg: str) -> None:
        self.console_messages.append(msg)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingLogger:
    recording = _RecordingLogger()
    monkeypatch.setattr("robot.api.logger.console", recording.console)
    return recording


def _robot_framework_with_console(monkeypatch: pytest.MonkeyPatch, recorder: _RecordingLogger) -> None:
    monkeypatch.setattr("JsonRpcRemote._LOGGER_WRITE_HAS_CONSOLE", True)
    monkeypatch.setattr("robot.api.logger.write", recorder.write_with_console)


def _robot_framework_without_console(monkeypatch: pytest.MonkeyPatch, recorder: _RecordingLogger) -> None:
    monkeypatch.setattr("JsonRpcRemote._LOGGER_WRITE_HAS_CONSOLE", False)
    monkeypatch.setattr("robot.api.logger.write", recorder.write_without_console)


def test_console_is_passed_to_write_where_supported(
    recorder: _RecordingLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    _robot_framework_with_console(monkeypatch, recorder)

    _write_log("message", "WARN", True, True)

    assert recorder.writes == [("message", "WARN", True, True)]
    assert recorder.console_messages == []


def test_console_message_is_written_separately_before_robot_framework_7_4(
    recorder: _RecordingLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    _robot_framework_without_console(monkeypatch, recorder)

    _write_log("message", "WARN", True, True)

    assert recorder.writes == [("message", "WARN", True)]
    assert recorder.console_messages == ["message"]


def test_message_without_console_stays_off_the_console_before_robot_framework_7_4(
    recorder: _RecordingLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    _robot_framework_without_console(monkeypatch, recorder)

    _write_log("message", "INFO", False, False)

    assert recorder.writes == [("message", "INFO", False)]
    assert recorder.console_messages == []


class _Written:
    """Replaces `_write_log` and records each message with the name of the thread that wrote it."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.messages: list[tuple[str, str]] = []
        # For each message: whether an event loop was running, as during a keyword call.
        self.during_call: list[bool] = []
        self._fail_on = fail_on

    def __call__(self, message: str, level: str, html: bool, console: bool) -> None:
        if message == self._fail_on:
            raise RuntimeError("writing failed")
        self.messages.append((message, threading.current_thread().name))
        try:
            asyncio.get_running_loop()
            self.during_call.append(True)
        except RuntimeError:
            self.during_call.append(False)


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> _Written:
    recording = _Written()
    monkeypatch.setattr("JsonRpcRemote._write_log", recording)
    return recording


@pytest.fixture
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    event_loop = asyncio.new_event_loop()
    try:
        yield event_loop
    finally:
        event_loop.close()


def _submit_from_worker(sink: _LogSink, *messages: str) -> None:
    def submit_all() -> None:
        for message in messages:
            sink.submit(message, "INFO", False, False)

    worker = threading.Thread(target=submit_all, name="worker")
    worker.start()
    worker.join()


def _run_pending_callbacks(loop: asyncio.AbstractEventLoop) -> None:
    loop.run_until_complete(asyncio.sleep(0))


def test_messages_wait_until_a_keyword_call_attaches(written: _Written, loop: asyncio.AbstractEventLoop) -> None:
    sink = _LogSink()
    _submit_from_worker(sink, "first", "second")
    assert written.messages == []

    sink.attach(loop)
    _submit_from_worker(sink, "third")
    _run_pending_callbacks(loop)

    main = threading.current_thread().name
    assert written.messages == [("first", main), ("second", main), ("third", main)]


def test_messages_after_detach_wait_for_the_next_drain(written: _Written, loop: asyncio.AbstractEventLoop) -> None:
    sink = _LogSink()
    sink.attach(loop)
    sink.detach()
    _submit_from_worker(sink, "late")
    _run_pending_callbacks(loop)
    assert written.messages == []

    sink.drain()

    assert written.messages == [("late", threading.current_thread().name)]


def test_drain_writes_on_the_calling_thread_in_arrival_order(written: _Written) -> None:
    sink = _LogSink()
    _submit_from_worker(sink, "first", "second")

    sink.drain()
    sink.drain()

    main = threading.current_thread().name
    assert written.messages == [("first", main), ("second", main)]


def test_drain_does_not_raise_when_a_write_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    failing = _Written(fail_on="broken")
    monkeypatch.setattr("JsonRpcRemote._write_log", failing)
    sink = _LogSink()
    _submit_from_worker(sink, "broken", "fine")

    sink.drain()

    assert failing.messages == [("fine", threading.current_thread().name)]


def test_message_for_a_closed_loop_waits_for_the_next_drain(written: _Written) -> None:
    closed = asyncio.new_event_loop()
    closed.close()
    sink = _LogSink()
    sink.attach(closed)

    _submit_from_worker(sink, "kept")
    sink.detach()
    sink.drain()

    assert written.messages == [("kept", threading.current_thread().name)]


@pytest.fixture
def server() -> Iterator[FakeServer]:
    with FakeServer() as fake:
        yield fake


def test_messages_from_the_import_are_written_when_the_import_returns(server: FakeServer, written: _Written) -> None:
    server.script(IMPORT_LIBRARY_REQUEST, LogFirst(("first", "second")))

    remote = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5)
    try:
        main = threading.current_thread().name
        assert written.messages == [("first", main), ("second", main)]
    finally:
        remote._stop_session()


def test_messages_of_a_failed_import_are_written_before_its_error(server: FakeServer, written: _Written) -> None:
    server.script(IMPORT_LIBRARY_REQUEST, LogFirst(("why it failed",), answer=RuntimeError("import failed")))

    with pytest.raises(Exception, match="import failed"):
        JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5)

    assert written.messages == [("why it failed", threading.current_thread().name)]


def test_messages_from_the_end_of_a_session_are_written_when_it_ends(server: FakeServer, written: _Written) -> None:
    server.script(FINALIZE_LIBRARY_REQUEST, LogFirst(("finalized",)))
    remote = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5)

    remote._stop_session()

    assert written.messages == [("finalized", threading.current_thread().name)]


def test_messages_from_a_reimport_are_written_during_the_keyword_call(server: FakeServer, written: _Written) -> None:
    remote = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5, rpc_scope=SessionScope.TEST)
    try:
        remote._stop_session()  # the end of the first test
        server.script(IMPORT_LIBRARY_REQUEST, LogFirst(("imported again",)))

        result = asyncio.run(remote.run_keyword("Echo", ["hello"], {}))

        assert result == "echo: hello"
        assert written.messages == [("imported again", threading.current_thread().name)]
        assert written.during_call == [True]
    finally:
        remote._stop_session()
