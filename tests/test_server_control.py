"""Unit tests for atests/ServerControl.py, the library that starts and stops the real server in the Robot suites."""

import importlib.util
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest


def _server_control() -> Any:
    path = Path(__file__).resolve().parent.parent / "atests" / "ServerControl.py"
    spec = importlib.util.spec_from_file_location("ServerControl", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ServerControl()


def _ended_process() -> "subprocess.Popen[bytes]":
    """Like a venv's launcher on Windows after a stop: it has ended, while the server behind it may still run."""
    process = subprocess.Popen([sys.executable, "-c", ""])
    process.wait(10)
    return process


@pytest.mark.parametrize("keyword", ["stop_jsonrpc_server", "kill_jsonrpc_server", "wait_for_jsonrpc_server_to_exit"])
def test_keyword_returns_only_when_the_port_is_closed(keyword: str) -> None:
    control = _server_control()
    listener = socket.create_server(("127.0.0.1", 0))
    control._port = listener.getsockname()[1]
    control._process = _ended_process()
    closer = threading.Timer(0.3, listener.close)

    started = time.monotonic()
    closer.start()
    try:
        getattr(control, keyword)()
        assert time.monotonic() - started >= 0.3
    finally:
        closer.join()


def test_port_that_stays_open_is_an_error() -> None:
    control = _server_control()
    with socket.create_server(("127.0.0.1", 0)) as listener:
        control._port = listener.getsockname()[1]

        with pytest.raises(RuntimeError, match="still accepts connections"):
            control._wait_until_port_is_closed(timeout=0.1)
