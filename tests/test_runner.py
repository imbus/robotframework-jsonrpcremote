"""Unit tests for the server's command runner: ``RobotRemoteContext`` and the error of a failed keyword.

The hook loop runs on its own thread without Robot, and the Robot calls behind the
commands are replaced by fakes.
"""

import asyncio
import datetime
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from robot.api import ContinuableFailure, FatalError, SkipExecution
from robot.errors import ExecutionFailed, HandlerExecutionFailed
from robot.result import Message
from robot.utils import ErrorDetails

from robot_jsonrpcremote_protocol import RunKeywordError, RunKeywordErrorMode
from robot_jsonrpcremote_server import _runner
from robot_jsonrpcremote_server._runner import RobotRemoteContext, _run_keyword_error


class _FakeRobot:
    """Stands in for running a keyword in Robot; ``Blocking`` waits until released."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.log_levels: list[str] = []
        self.blocking = threading.Event()
        self.release = threading.Event()

    def set_log_level(self, level: str) -> None:
        self.log_levels.append(level)

    def run_keyword(self, library_token: str, name: str, args: Any, kwargs: Any) -> str:
        self.calls.append(name)
        if name == "Blocking":
            self.blocking.set()
            self.release.wait(5)
        return f"result of {name}"


@pytest.fixture
def robot(monkeypatch: pytest.MonkeyPatch) -> _FakeRobot:
    fake = _FakeRobot()
    monkeypatch.setattr(_runner, "_robot_run_keyword", fake.run_keyword)
    monkeypatch.setattr(_runner, "_robot_set_log_level", fake.set_log_level)
    return fake


@pytest.fixture
def context(robot: _FakeRobot) -> Iterator[RobotRemoteContext]:
    """A context whose hook loop runs on its own thread, the one that created it, as in the server."""
    created: list[RobotRemoteContext] = []
    ready = threading.Event()

    def run_hook_loop() -> None:
        created.append(RobotRemoteContext())
        ready.set()
        created[0]._hook_loop()

    thread = threading.Thread(target=run_hook_loop, daemon=True)
    thread.start()
    assert ready.wait(5)
    try:
        yield created[0]
    finally:
        created[0].stop()
        robot.release.set()
        thread.join(5)


async def test_stop_completes_the_running_command_and_fails_the_queued_one(
    context: RobotRemoteContext, robot: _FakeRobot
) -> None:
    running = asyncio.ensure_future(context.run_keyword("token", "Blocking", [], {}))
    await asyncio.to_thread(robot.blocking.wait, 5)
    queued = asyncio.ensure_future(context.run_keyword("token", "Queued", [], {}))
    await asyncio.sleep(0)  # lets the queued call reach the queue

    context.stop()
    robot.release.set()

    assert await asyncio.wait_for(running, 5) == "result of Blocking"
    with pytest.raises(RuntimeError, match=r"^server is shutting down$"):
        await asyncio.wait_for(queued, 5)
    assert robot.calls == ["Blocking"]


async def test_submission_after_stop_fails_at_once(context: RobotRemoteContext, robot: _FakeRobot) -> None:
    context.stop()

    with pytest.raises(RuntimeError, match=r"^server is shutting down$"):
        await asyncio.wait_for(context.run_keyword("token", "Late", [], {}), 1)
    with pytest.raises(RuntimeError, match=r"^server is shutting down$"):
        await asyncio.wait_for(context.import_library("Lib", [], "token"), 1)
    with pytest.raises(RuntimeError, match=r"^server is shutting down$"):
        await asyncio.wait_for(context.finalize_library("token"), 1)
    assert robot.calls == []


class _Subscriber:
    """Stands in for the endpoint of a client: it has a log level and records the forwarded messages."""

    def __init__(self, log_level: str = "INFO") -> None:
        self.log_level = log_level
        self.messages: list[tuple[str, str]] = []

    def log_message(self, message: str, level: str, html: bool, timestamp: datetime.datetime) -> None:
        self.messages.append((level, message))


async def test_a_command_runs_at_the_log_level_of_its_subscriber(
    context: RobotRemoteContext, robot: _FakeRobot
) -> None:
    await asyncio.wait_for(context.run_keyword("token", "Keyword", [], {}, subscriber=_Subscriber("DEBUG")), 5)
    await asyncio.wait_for(context.run_keyword("token", "Keyword", [], {}, subscriber=_Subscriber("TRACE")), 5)
    await asyncio.wait_for(context.run_keyword("token", "Keyword", [], {}), 5)

    assert robot.log_levels == ["DEBUG", "TRACE", "INFO"]
    assert robot.calls == ["Keyword", "Keyword", "Keyword"]


async def test_a_command_at_an_invalid_log_level_fails_and_does_not_run(
    context: RobotRemoteContext, robot: _FakeRobot, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(level: str) -> None:
        raise ValueError(f"Invalid log level '{level}'.")

    monkeypatch.setattr(_runner, "_robot_set_log_level", reject)

    with pytest.raises(ValueError, match="Invalid log level 'BOGUS'"):
        await asyncio.wait_for(context.run_keyword("token", "Keyword", [], {}, subscriber=_Subscriber("BOGUS")), 5)
    assert robot.calls == []


def _log(context: RobotRemoteContext, *messages: tuple[str, str]) -> None:
    for level, text in messages:
        context._log_message(Message(text, level))


@pytest.mark.parametrize("failure_level", ["FAIL", "SKIP"])
def test_traceback_of_a_failure_is_not_forwarded(failure_level: str) -> None:
    context = RobotRemoteContext()
    subscriber = _Subscriber()
    context._active_subscriber = subscriber

    _log(
        context,
        ("DEBUG", "of the library"),
        (failure_level, "boom"),
        ("DEBUG", "the traceback"),
        ("DEBUG", "of the library, too"),
    )

    assert subscriber.messages == [
        ("DEBUG", "of the library"),
        (failure_level, "boom"),
        ("DEBUG", "of the library, too"),
    ]


async def test_first_debug_message_of_a_command_is_no_traceback_of_the_command_before(
    context: RobotRemoteContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    subscriber = _Subscriber()
    batches = iter([[("FAIL", "a failure without a traceback")], [("DEBUG", "of the library")]])
    monkeypatch.setattr(_runner, "_robot_run_keyword", lambda *args: _log(context, *next(batches)))

    await asyncio.wait_for(context.run_keyword("token", "First", [], {}, subscriber=subscriber), 5)
    await asyncio.wait_for(context.run_keyword("token", "Second", [], {}, subscriber=subscriber), 5)

    assert subscriber.messages == [("FAIL", "a failure without a traceback"), ("DEBUG", "of the library")]


def _failure_of(error: Exception) -> ExecutionFailed:
    """The failure that Robot's status reporter raises for a local keyword that raises ``error``."""

    def keyword() -> None:
        raise error

    try:
        try:
            keyword()
        except Exception as original:
            # Like the status reporter: the original exception stays the failure's __context__.
            raise HandlerExecutionFailed(ErrorDetails(original))
    except ExecutionFailed as failure:
        return failure
    raise AssertionError("the keyword did not raise")


def test_error_of_a_value_error_has_the_message_of_a_local_keyword() -> None:
    assert _run_keyword_error(_failure_of(ValueError("bad value"))).message == "ValueError: bad value"


def test_error_of_an_assertion_has_the_message_of_a_local_keyword() -> None:
    assert _run_keyword_error(_failure_of(AssertionError("boom"))).message == "boom"


def test_error_names_the_type_and_carries_the_traceback_of_the_library_code() -> None:
    error = _run_keyword_error(_failure_of(ValueError("bad value")))

    assert error.type == "ValueError"
    assert error.traceback is not None
    assert error.traceback.startswith("Traceback (most recent call last):")
    assert "raise error" in error.traceback
    assert error.traceback.endswith("ValueError: bad value")


@pytest.mark.parametrize(
    ("raised", "mode"),
    [
        (SkipExecution("not today"), RunKeywordErrorMode.SKIP),
        (ContinuableFailure("go on"), RunKeywordErrorMode.CONTINUABLE),
        (FatalError("stop all"), RunKeywordErrorMode.FATAL),
        (ValueError("bad value"), None),
    ],
)
def test_error_carries_the_failure_mode(raised: Exception, mode: RunKeywordErrorMode | None) -> None:
    assert _run_keyword_error(_failure_of(raised)).mode is mode


def test_failure_mode_prefers_skip_over_fatal_over_continuable() -> None:
    skip_and_fatal = ExecutionFailed("message", skip=True, exit=True)
    fatal_and_continuable = ExecutionFailed("message", exit=True, continue_on_failure=True)

    assert _run_keyword_error(skip_and_fatal).mode is RunKeywordErrorMode.SKIP
    assert _run_keyword_error(fatal_and_continuable).mode is RunKeywordErrorMode.FATAL


def test_error_of_a_failure_without_an_exception_has_only_the_message() -> None:
    assert _run_keyword_error(ExecutionFailed("several failures")) == RunKeywordError(message="several failures")
