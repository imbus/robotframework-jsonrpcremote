"""The examples of the documentation site, run with the commands of their pages, on every system.

Each test runs one folder of ``docs/examples`` as its page describes it: it starts the server where
the page starts one, runs ``robot`` with the suites of the example, and stops the server again.
"""

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import pytest
from robot.api import ExecutionResult

from jsonrpcpeer import open_pipe_connection

_EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "examples"
_PORT = 8271
# The console scripts of the interpreter that runs the tests, also when its folder is not on PATH.
_SCRIPTS = str(Path(sys.executable).parent)


def _path() -> str:
    return os.pathsep.join([_SCRIPTS, os.environ.get("PATH", "")])


def _command(name: str) -> str:
    """The console script ``name``, as a reader runs it: next to the interpreter first, then on PATH."""
    found = shutil.which(name, path=_path())
    assert found is not None, f"{name} is not installed"
    return found


def _environment(outputs: Path | None = None) -> dict[str, str]:
    """The environment of a command: the console scripts on PATH, and the outputs of robot in ``outputs``."""
    environment = {**os.environ, "PATH": _path()}
    if outputs is not None:
        # As an option of the environment, so that the command stays as on the page.
        environment["ROBOT_OPTIONS"] = f'--outputdir "{outputs}"'
    return environment


def _port_open() -> bool:
    try:
        socket.create_connection(("127.0.0.1", _PORT), 1).close()
    except OSError:
        return False
    return True


def _pipe_open(name: str) -> bool:
    """Whether a server listens on the pipe ``name``."""

    async def connect() -> None:
        _, writer = await asyncio.wait_for(open_pipe_connection(name), 1)
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()

    try:
        asyncio.run(connect())
    except OSError:
        return False
    return True


@contextmanager
def _server(folder: Path, log: Path, *command: str, listening: Callable[[], bool] = _port_open) -> Iterator[None]:
    """Run ``command`` in ``folder`` as the server while the block runs, by default on port 8271."""
    with log.open("wb") as output:
        process = subprocess.Popen(
            [_command(command[0]), *command[1:]],
            cwd=folder,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=_environment(),
        )
    try:
        deadline = time.monotonic() + 10
        while not listening():
            if process.poll() is not None or time.monotonic() > deadline:
                pytest.fail(f"{command[0]} did not start:\n{log.read_text(errors='replace')}")
            time.sleep(0.1)
        yield
    finally:
        # SIGTERM on POSIX, which the server takes as a graceful stop; on Windows, a hard stop.
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(10)
        # The next example binds the same port.
        deadline = time.monotonic() + 10
        while listening() and time.monotonic() < deadline:
            time.sleep(0.1)


def _start_robot(folder: Path, outputs: Path, *arguments: str) -> "subprocess.Popen[bytes]":
    with (outputs / "console.txt").open("wb") as console:
        return subprocess.Popen(
            [_command("robot"), *arguments],
            cwd=folder,
            stdout=console,
            stderr=subprocess.STDOUT,
            env=_environment(outputs),
        )


def _result(outputs: Path) -> Any:
    output = outputs / "output.xml"
    assert output.exists(), (outputs / "console.txt").read_text(errors="replace")
    return ExecutionResult(str(output))


def _robot(folder: Path, outputs: Path, *arguments: str) -> tuple[int, Any]:
    """Run ``robot`` in ``folder`` with ``arguments``; return its exit code and its result."""
    process = _start_robot(folder, outputs, *arguments)
    try:
        code = process.wait(120)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    return code, _result(outputs)


def _failed(result: Any) -> list[tuple[str, str, str]]:
    return [(test.name, test.status, test.message) for test in result.suite.all_tests if test.status != "PASS"]


def test_getting_started(tmp_path: Path) -> None:
    folder = _EXAMPLES / "getting-started"
    with _server(folder, tmp_path / "server.txt", "robot-jsonrpcremote-server", "--pythonpath", ".", "MyLibrary"):
        code, result = _robot(folder, tmp_path, "greet.robot")

    assert code == 0, _failed(result)


_FAILURES = {
    "Normal Failure": ("FAIL", "ValueError: bad value"),
    "Skipped": ("SKIP", "not today"),
    "Continuable Failure": ("FAIL", "go on"),
    "Fatal Failure": ("FAIL", "FatalError: stop all"),
    "Not Run": ("FAIL", "Test execution stopped due to a fatal error."),
}


def test_failures(tmp_path: Path) -> None:
    folder = _EXAMPLES / "failures"
    with _server(folder, tmp_path / "server.txt", "robot-jsonrpcremote-server", "--pythonpath", ".", "FailingLibrary"):
        # Twice: the server keeps running after the fatal failure.
        for _ in range(2):
            _, result = _robot(folder, tmp_path, "--loglevel", "DEBUG", "failures.robot")
            tests = {test.name: test for test in result.suite.all_tests}
            assert {name: (test.status, test.message) for name, test in tests.items()} == _FAILURES

            normal_failure = tests["Normal Failure"].body
            assert normal_failure[1].status == "NOT RUN"
            tracebacks = [
                message.message
                for message in normal_failure[0].body
                if message.level == "DEBUG" and "Traceback" in message.message
            ]
            assert len(tracebacks) == 1, tracebacks
            assert tracebacks[0].startswith("[remote] Traceback"), tracebacks
            assert 'raise ValueError("bad value")' in tracebacks[0], tracebacks
            assert tests["Continuable Failure"].body[1].status == "PASS"

        # The server does not serve this library: the import fails with its message, as the page says.
        _, result = _robot(folder, tmp_path, "refused_import.robot")

    errors = [message.message.strip() for message in result.errors.messages]
    assert len(errors) == 1, errors
    assert errors[0].endswith("failed: Library 'OtherLibrary' is not available."), errors
    assert "RPC Error" not in errors[0], errors
    assert "Traceback" not in errors[0], errors


def test_own_server(tmp_path: Path) -> None:
    folder = _EXAMPLES / "own-server"
    # The hand-written server of examples/simple-robot-jsonrpcserver.
    with _server(folder, tmp_path / "server.txt", "simple-robot-jsonrpcserver"):
        code, result = _robot(folder, tmp_path, "echo.robot")
    assert code == 0, _failed(result)

    # The same server over stdio and over a pipe: the client starts it for the suite.
    code, result = _robot(folder, tmp_path, "echo_stdio.robot")
    assert code == 0, _failed(result)
    code, result = _robot(folder, tmp_path, "echo_pipe.robot")
    assert code == 0, _failed(result)


def test_rpc_scope(tmp_path: Path) -> None:
    folder = _EXAMPLES / "rpc-scope"
    with _server(folder, tmp_path / "server.txt", "robot-jsonrpcremote-server", "--pythonpath", ".", "Counter"):
        code, result = _robot(folder, tmp_path, "counter.robot")

    assert code == 0, _failed(result)


def test_several_libraries(tmp_path: Path) -> None:
    folder = _EXAMPLES / "several-libraries"
    # One server for both libraries.
    with _server(
        folder, tmp_path / "server.txt", "robot-jsonrpcremote-server", "--pythonpath", ".", "MyLibrary", "Calculator"
    ):
        code, result = _robot(folder, tmp_path, "two-libraries.robot")

    assert code == 0, _failed(result)


def test_connect_retry(tmp_path: Path) -> None:
    folder = _EXAMPLES / "connect-retry"
    # The suite starts first: its library import waits for the server.
    suite = _start_robot(folder, tmp_path, "greet.robot")
    try:
        # The server starts a few seconds later, as a container that is still starting would.
        time.sleep(3)
        with _server(folder, tmp_path / "server.txt", "robot-jsonrpcremote-server", "--pythonpath", ".", "MyLibrary"):
            code = suite.wait(120)
    finally:
        if suite.poll() is None:
            suite.kill()
            suite.wait()
    result = _result(tmp_path)

    assert code == 0, _failed(result)


def test_pipe(tmp_path: Path) -> None:
    # No server to start: the client starts it for the suite and stops it afterwards.
    code, result = _robot(_EXAMPLES / "pipe", tmp_path, "greet.robot")
    assert code == 0, _failed(result)

    # The same with the command as a list.
    code, result = _robot(_EXAMPLES / "pipe", tmp_path, "greet_list.robot")
    assert code == 0, _failed(result)


def test_pipe_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _EXAMPLES / "pipe-server"
    # The name is relative to the working directory, of the server, of robot and of the wait for the server.
    monkeypatch.chdir(folder)
    with _server(
        folder,
        tmp_path / "server.txt",
        "robot-jsonrpcremote-server",
        "--pipe-server",
        "robot.sock",
        "--pythonpath",
        ".",
        "MyLibrary",
        listening=lambda: _pipe_open("robot.sock"),
    ):
        code, result = _robot(folder, tmp_path, "greet.robot")

    assert code == 0, _failed(result)
    assert not (folder / "robot.sock").exists()


def test_stdio(tmp_path: Path) -> None:
    # No server to start: the client starts it for the suite and stops it afterwards.
    code, result = _robot(_EXAMPLES / "stdio", tmp_path, "greet.robot")

    assert code == 0, _failed(result)


def _container_tools() -> tuple[str, str]:
    """``docker`` and ``uv``, or skip: they run Linux containers on Linux, and on other systems only sometimes."""
    docker, uv = shutil.which("docker"), shutil.which("uv")
    if sys.platform.startswith("linux"):
        if docker is None or uv is None:
            if os.environ.get("CI"):
                pytest.fail("docker and uv are needed, and the Linux runners of CI have them")
            pytest.skip("needs docker and uv")
    elif docker is None or uv is None:
        pytest.skip("needs docker with Linux containers, and uv")
    else:
        # Docker Desktop can run Linux containers; the Windows runners of CI only run Windows containers.
        kind = subprocess.run(
            [docker, "info", "--format", "{{.OSType}}"], capture_output=True, text=True, timeout=60, check=False
        )
        if kind.stdout.strip() != "linux":
            pytest.skip("needs docker with Linux containers")
    assert docker is not None
    assert uv is not None
    return docker, uv


def test_container(tmp_path: Path) -> None:
    docker, uv = _container_tools()
    folder = _EXAMPLES / "container"
    # The image installs the wheels of the current code from its build context, instead of the release on PyPI.
    wheels = folder / "wheels"
    shutil.rmtree(wheels, ignore_errors=True)
    for package in ("jsonrpcpeer", "robotframework-jsonrpcremote-protocol", "robotframework-jsonrpcremote-server"):
        subprocess.run(
            [uv, "build", "--package", package, "--wheel", "-o", str(wheels)],
            cwd=folder,
            check=True,
            capture_output=True,
            timeout=300,
        )
    subprocess.run(
        [docker, "build", "--tag", "my-library-server", "--build-arg", "PACKAGES=/context/wheels/*.whl", "."],
        cwd=folder,
        check=True,
        capture_output=True,
        timeout=600,
    )

    # The server, with its port published on the loopback address of this machine only, as the page starts it.
    subprocess.run(
        [
            docker,
            "run",
            "--detach",
            "--rm",
            "--name",
            "my-library-server",
            "--publish",
            "127.0.0.1:8271:8271",
            "my-library-server",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    try:
        # The published port accepts connections before the server listens, so wait for its message.
        deadline = time.monotonic() + 30
        while True:
            logs = subprocess.run(
                [docker, "logs", "my-library-server"], capture_output=True, text=True, timeout=60, check=False
            )
            if "Server is up and running" in logs.stdout + logs.stderr:
                break
            assert time.monotonic() < deadline, logs.stdout + logs.stderr
            time.sleep(0.2)
        # The suite from Getting started.
        code, result = _robot(_EXAMPLES / "getting-started", tmp_path, "greet.robot")
    finally:
        subprocess.run([docker, "stop", "my-library-server"], capture_output=True, timeout=120, check=False)

    assert code == 0, _failed(result)
