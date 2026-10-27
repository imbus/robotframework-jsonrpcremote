import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from robot_jsonrpcremote_server.__main__ import _parse_addresses, build_arg_parser, run

# --- _parse_addresses ------------------------------------------------------


def test_parse_addresses_none_and_empty() -> None:
    assert _parse_addresses(None) is None
    assert _parse_addresses("") is None
    assert _parse_addresses("   ") is None


def test_parse_addresses_splits_and_strips() -> None:
    assert _parse_addresses("a, b ,c") == ["a", "b", "c"]
    assert _parse_addresses("127.0.0.1") == ["127.0.0.1"]


# --- argument parsing ------------------------------------------------------


def test_libraries_are_positional() -> None:
    args = build_arg_parser().parse_args(["MyLib", "OtherLib"])
    assert args.libraries == ["MyLib", "OtherLib"]
    assert args.mode == "tcp"


def test_port_and_bind() -> None:
    args = build_arg_parser().parse_args(["--port", "9000", "--bind", "0.0.0.0", "--bind", "127.0.0.1", "Lib"])
    assert args.port == 9000
    assert args.addresses == ["0.0.0.0", "127.0.0.1"]


def test_robot_options() -> None:
    args = build_arg_parser().parse_args(
        ["--variable", "A:1", "--variable", "B:2", "-V", "vars.py", "-d", "out", "-P", "d1", "-P", "d2", "Lib"]
    )
    assert args.variable == ["A:1", "B:2"]
    assert args.variablefile == ["vars.py"]
    assert args.outputdir == "out"
    assert args.pythonpath == ["d1", "d2"]


def test_mode_aliases() -> None:
    assert build_arg_parser().parse_args(["--pipe", "Lib"]).mode == "pipe"
    assert build_arg_parser().parse_args(["--stdio", "Lib"]).mode == "stdio"
    assert build_arg_parser().parse_args(["--tcp", "Lib"]).mode == "tcp"


# --- run() rejects unsupported modes cleanly -------------------------------


@pytest.mark.parametrize("flag", ["--pipe"])
def test_run_rejects_unsupported_mode(flag: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["robot-jsonrpcremote-server", flag, "MyLib"])
    with pytest.raises(SystemExit) as excinfo:
        run()
    assert excinfo.value.code == 2


# --- run() reports a failed start ------------------------------------------


def _run_server(*args: str, **options: Any) -> tuple["subprocess.CompletedProcess[str]", float]:
    """Run the real server as a subprocess until it exits; return its result and how long it ran."""
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "robot_jsonrpcremote_server", *args],
        capture_output=True,
        text=True,
        timeout=30,
        **options,
    )
    return result, time.monotonic() - started


def test_server_on_a_port_in_use_fails_to_start() -> None:
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]

        result, seconds = _run_server("--port", str(port), "SomeLib")

    assert result.returncode == 1
    assert seconds < 5, "the server waited for a start timeout"
    assert "Server failed to start" in result.stderr
    assert f"('127.0.0.1', {port})" in result.stderr
    assert "up and running" not in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="the stdio transport is POSIX-only")
@pytest.mark.parametrize("stdin", ["/dev/null", "regular file"])
def test_stdio_server_with_a_stdin_that_cannot_be_watched_fails_to_start(stdin: str, tmp_path: Path) -> None:
    path = Path(os.devnull)
    if stdin == "regular file":
        path = tmp_path / "stdin.txt"
        path.write_text("")

    with path.open() as file:
        result, seconds = _run_server("--stdio", "SomeLib", stdin=file)

    assert result.returncode == 1
    assert seconds < 5, "the server waited instead of failing"
    assert "Server failed to start: stdio mode needs a stdin that can be watched for input" in result.stderr
    assert "up and running" not in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="the stdio transport is POSIX-only")
def test_stdio_server_with_a_closed_pipe_on_stdin_ends_normally() -> None:
    # `input` writes nothing and closes the pipe: the server starts and sees the end of its input.
    result, _ = _run_server("--stdio", "SomeLib", input="")

    assert result.returncode == 0
    assert "Server failed to start" not in result.stderr
