"""Unit tests for the server's command runner (``RobotRemoteContext``) while it stops.

The hook loop runs on its own thread without Robot, and the Robot calls behind the
commands are replaced by fakes.
"""

import asyncio
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from robot_jsonrpcremote_server import _runner
from robot_jsonrpcremote_server._runner import RobotRemoteContext


class _FakeRobot:
    """Stands in for running a keyword in Robot; ``Blocking`` waits until released."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.blocking = threading.Event()
        self.release = threading.Event()

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
