import asyncio
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from server_over_pipes import TIMEOUT, connect_when_listening, echo, end, start_server

from jsonrpcpeer import open_pipe_connection, start_pipe_server
from robot_jsonrpcremote_server.__main__ import _parse_addresses, build_arg_parser

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


def test_outputdir_help_says_that_the_server_writes_no_output_files() -> None:
    help_text = " ".join(build_arg_parser().format_help().split())
    assert "Set ${OUTPUT_DIR} for the libraries" in help_text
    assert "the server writes no output files" in help_text


def test_tracebacks_are_only_sent_with_the_option() -> None:
    assert build_arg_parser().parse_args(["Lib"]).send_tracebacks is False
    assert build_arg_parser().parse_args(["--send-tracebacks", "Lib"]).send_tracebacks is True


def test_mode_aliases() -> None:
    assert build_arg_parser().parse_args(["--stdio", "Lib"]).mode == "stdio"
    assert build_arg_parser().parse_args(["--tcp", "Lib"]).mode == "tcp"


@pytest.mark.parametrize(
    ("argv", "mode"),
    [
        pytest.param(["--pipe", "robot", "Lib"], "pipe", id="pipe_with_the_name_as_the_next_argument"),
        pytest.param(["--pipe=robot", "Lib"], "pipe", id="pipe_with_an_equals_sign"),
        pytest.param(["Lib", "--pipe=robot"], "pipe", id="pipe_as_the_last_argument"),
        pytest.param(["--mode", "pipe", "--pipe-name", "robot", "Lib"], "pipe", id="mode_pipe"),
        pytest.param(
            ["--pipe-server", "robot", "Lib"], "pipe-server", id="pipe_server_with_the_name_as_the_next_argument"
        ),
        pytest.param(["--pipe-server=robot", "Lib"], "pipe-server", id="pipe_server_with_an_equals_sign"),
        pytest.param(["--mode", "pipe-server", "--pipe-name", "robot", "Lib"], "pipe-server", id="mode_pipe_server"),
    ],
)
def test_the_options_of_a_pipe_mode_set_the_mode_and_the_name(
    server_environment: pytest.MonkeyPatch, argv: list[str], mode: str
) -> None:
    args = build_arg_parser().parse_args(argv)

    assert (args.mode, args.pipe_name, args.libraries) == (mode, "robot", ["Lib"])


def test_the_help_names_no_planned_mode() -> None:
    help_text = " ".join(build_arg_parser().format_help().split())

    assert "planned" not in help_text
    assert "not yet implemented" not in help_text
    assert "--pipe NAME" in help_text
    assert "--pipe-server NAME" in help_text


# --- configure_logging ------------------------------------------------------


def test_level_of_the_root_logger_does_not_change_what_the_server_prints() -> None:
    # In its own process: basicConfig() does nothing here, where pytest has configured logging.
    code = """
import logging
from robot_jsonrpcremote_server.__main__ import configure_logging

configure_logging(verbose=False)
logging.getLogger().setLevel(logging.DEBUG)  # what Robot does for a client at DEBUG
logging.getLogger("library").debug("hidden")
logging.getLogger("library").info("shown")
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, check=True)

    assert result.stderr.splitlines() == ["[INFO] shown"]


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


def test_server_on_a_pipe_that_nobody_listens_on_fails_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    name = f"robot-test-{secrets.token_hex(8)}"

    result, seconds = _run_server("--pipe", name, "SomeLib")

    assert result.returncode == 1
    assert seconds < 5, "the server waited for a start timeout"
    assert "Server failed to start" in result.stderr
    assert name in result.stderr
    assert "up and running" not in result.stderr


async def test_server_on_a_pipe_name_in_use_fails_to_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    name = f"robot-test-{secrets.token_hex(8)}"

    async def close(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    other = await start_pipe_server(close, name)
    try:
        process = await start_server("--pipe-server", name)
        try:
            code = await asyncio.wait_for(process.wait(), TIMEOUT)
        finally:
            stderr = await end(process)
        # The other server still accepts clients.
        _, writer = await asyncio.wait_for(open_pipe_connection(name), TIMEOUT)
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), TIMEOUT)
    finally:
        other.close()
        # Until its connections have ended, also off Windows: a transport that outlives its server makes asyncio of
        # Python 3.13 and later report a TypeError once it is collected.
        await asyncio.wait_for(other.wait_closed(), TIMEOUT)

    assert code == 1, stderr
    assert "Server failed to start" in stderr
    assert name in stderr
    assert "up and running" not in stderr


@pytest.mark.parametrize("stdin", ["null device", "regular file"])
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


def test_stdio_server_with_a_closed_pipe_on_stdin_ends_normally() -> None:
    # `input` writes nothing and closes the pipe: the server starts and sees the end of its input. On Windows, the
    # pipe of subprocess is synchronous, so the server reads it in a thread.
    result, _ = _run_server("--stdio", "SomeLib", input="")

    assert result.returncode == 0
    assert "Server failed to start" not in result.stderr


# --- values from the environment --------------------------------------------


def _environment(**values: str) -> dict[str, str]:
    """``os.environ`` without the variables of the server, with ``values`` added."""
    environment = {name: value for name, value in os.environ.items() if not name.startswith("ROBOT_JSONRPC_")}
    environment.update(values)
    return environment


@pytest.fixture
def server_environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A monkeypatch without the variables of the server, for parsers built in this process."""
    for name in list(os.environ):
        if name.startswith("ROBOT_JSONRPC_"):
            monkeypatch.delenv(name)
    return monkeypatch


def test_invalid_port_from_the_environment_is_a_usage_error() -> None:
    result, _ = _run_server("SomeLib", env=_environment(ROBOT_JSONRPC_PORT="abc"))

    assert result.returncode == 2
    assert "--port" in result.stderr
    assert "'abc'" in result.stderr
    assert "Traceback" not in result.stderr
    assert "up and running" not in result.stderr


def test_port_from_the_environment_is_a_number(server_environment: pytest.MonkeyPatch) -> None:
    assert build_arg_parser().parse_args(["Lib"]).port == 8271

    server_environment.setenv("ROBOT_JSONRPC_PORT", "9001")

    assert build_arg_parser().parse_args(["Lib"]).port == 9001


def test_command_line_takes_precedence_over_an_invalid_environment(server_environment: pytest.MonkeyPatch) -> None:
    server_environment.setenv("ROBOT_JSONRPC_PORT", "abc")
    server_environment.setenv("ROBOT_JSONRPC_MODE", "tpc")

    args = build_arg_parser().parse_args(["--port", "9000", "--stdio", "Lib"])

    assert args.port == 9000
    assert args.mode == "stdio"


def test_unknown_mode_from_the_environment_is_a_usage_error() -> None:
    result, _ = _run_server("SomeLib", env=_environment(ROBOT_JSONRPC_MODE="tpc"))

    assert result.returncode == 2
    for text in ("--mode", "'tpc'", "tcp", "stdio", "pipe", "pipe-server"):
        assert text in result.stderr
    assert "Traceback" not in result.stderr


def test_pickles_turned_off_from_the_environment(server_environment: pytest.MonkeyPatch) -> None:
    assert build_arg_parser().parse_args(["Lib"]).pickles is True

    server_environment.setenv("ROBOT_JSONRPC_PICKLES", "no")

    assert build_arg_parser().parse_args(["Lib"]).pickles is False


def test_command_line_takes_precedence_for_pickles(server_environment: pytest.MonkeyPatch) -> None:
    server_environment.setenv("ROBOT_JSONRPC_PICKLES", "off")

    assert build_arg_parser().parse_args(["--pickles", "Lib"]).pickles is True


def test_pickles_value_from_the_environment_that_is_no_truth_value_is_a_usage_error() -> None:
    result, _ = _run_server("SomeLib", env=_environment(ROBOT_JSONRPC_PICKLES="maybe"))

    assert result.returncode == 2
    assert "ROBOT_JSONRPC_PICKLES" in result.stderr
    assert "'maybe'" in result.stderr
    assert "Traceback" not in result.stderr
    assert "up and running" not in result.stderr


async def test_pipe_mode_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    name = f"robot-test-{secrets.token_hex(8)}"

    process = await start_server(env=_environment(ROBOT_JSONRPC_MODE="pipe-server", ROBOT_JSONRPC_PIPE_NAME=name))
    try:
        result = await echo(*await connect_when_listening(name, process), "from the environment")
    finally:
        stderr = await end(process)

    assert result == "echo: from the environment", stderr


def _error_line(capsys: pytest.CaptureFixture[str], *args: str) -> str:
    """The error line that parsing ``args`` writes."""
    with pytest.raises(SystemExit):
        build_arg_parser().parse_args(list(args))
    return capsys.readouterr().err.splitlines()[-1]


def test_unknown_mode_gives_the_same_error_from_both_sources(
    server_environment: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from_command_line = _error_line(capsys, "--mode", "tpc", "Lib")
    server_environment.setenv("ROBOT_JSONRPC_MODE", "tpc")
    from_environment = _error_line(capsys, "Lib")

    assert "invalid choice: 'tpc'" in from_command_line
    assert from_environment == from_command_line
