"""Our server in its pipe modes, as a process of its own.

In pipe mode, the server connects to the pipe of a client that has started it, as
``create_pipe_subprocess()`` starts it. In pipe-server mode, it listens on a pipe for any number of
clients. The tests change into a directory of their own and use relative names there, as the tests
of ``jsonrpcpeer`` do.
"""

import asyncio
import os
import secrets
import signal
import sys
from pathlib import Path

import pytest
from server_over_pipes import TIMEOUT, connect_when_listening, echo, end, server_command, start_server, wait_until_up

from jsonrpcpeer import JsonRpcPeer, create_pipe_subprocess, pipe_address


@pytest.fixture(autouse=True)
def _in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def name() -> str:
    return f"robot-test-{secrets.token_hex(8)}"


# pipe mode


async def test_the_server_serves_the_client_whose_pipe_it_connects_to() -> None:
    process, reader, writer = await asyncio.wait_for(
        create_pipe_subprocess(*server_command(), stdin=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE),
        TIMEOUT,
    )
    try:
        result = await echo(reader, writer, "over a pipe")
        # The end of the connection stops the server.
        code = await asyncio.wait_for(process.wait(), TIMEOUT)
    finally:
        stderr = await end(process)

    assert result == "echo: over a pipe", stderr
    assert code == 0, stderr
    assert "serving the client of the pipe" in stderr


# pipe-server mode


async def test_two_clients_at_once_get_the_results_of_their_keywords(name: str) -> None:
    process = await start_server("--pipe-server", name)
    try:
        first = await connect_when_listening(name, process)
        second = await connect_when_listening(name, process)
        results = await asyncio.gather(echo(*first, "first"), echo(*second, "second"))
    finally:
        stderr = await end(process)

    assert list(results) == ["echo: first", "echo: second"], stderr


async def test_the_log_names_the_pipe_that_the_server_listens_on(name: str) -> None:
    process = await start_server("--pipe-server", name)
    try:
        _, writer = await connect_when_listening(name, process)
        writer.close()
    finally:
        stderr = await end(process)

    # A named pipe on Windows, the socket file in the working directory elsewhere.
    assert f"listening on the pipe {pipe_address(name)}\n" in stderr.replace("\r\n", "\n")


@pytest.mark.skipif(sys.platform == "win32", reason="terminate() is a hard kill on Windows")
@pytest.mark.parametrize("stop", ["SIGINT", "SIGTERM"])
async def test_a_signal_stops_the_server_and_its_socket_file_is_gone(tmp_path: Path, name: str, stop: str) -> None:
    process = await start_server("--pipe-server", name)
    try:
        await wait_until_up(process)
        peer = JsonRpcPeer(*await connect_when_listening(name, process))
        peer.start()
        # Answered, so the server serves the connection.
        await asyncio.wait_for(peer.send_request("robot/initialize", {}), TIMEOUT)
        process.send_signal(getattr(signal, stop))
        # The server closes the connection, and exits.
        closed = await asyncio.wait_for(peer.completion, TIMEOUT)
        code = await asyncio.wait_for(process.wait(), TIMEOUT)
    finally:
        stderr = await end(process)

    assert closed is True, stderr
    assert code == 0, stderr
    assert not os.path.exists(tmp_path / name), stderr
