"""Our server over a pipe, for the tests of its pipe modes (a helper, not collected by pytest)."""

import asyncio
import os
import sys
from contextlib import suppress

from jsonrpcpeer import JsonRpcPeer, open_pipe_connection
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    INITIALIZED_NOTIFICATION,
    RUN_KEYWORD_REQUEST,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    RunKeywordParams,
    RunKeywordResult,
)

ATESTS_LIBRARIES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "atests", "libraries"))
# A hard limit for every wait, so that a server that never answers fails the test instead of hanging it.
TIMEOUT = 30


def server_command(*args: str) -> list[str]:
    """The command that starts our server with ``StdioEchoLib`` and the further ``args``."""
    return [sys.executable, "-m", "robot_jsonrpcremote_server", "--pythonpath", ATESTS_LIBRARIES, *args, "StdioEchoLib"]


async def start_server(*args: str, env: dict[str, str] | None = None) -> asyncio.subprocess.Process:
    """Our server as a process of its own, with an empty stdin and its stderr in a pipe."""
    return await asyncio.create_subprocess_exec(
        *server_command(*args), stdin=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=env
    )


async def connect_when_listening(
    name: str, process: asyncio.subprocess.Process
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the pipe ``name`` as soon as the server listens there."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TIMEOUT
    while True:
        try:
            return await asyncio.wait_for(open_pipe_connection(name), TIMEOUT)
        except OSError:
            if process.returncode is not None or loop.time() > deadline:
                raise
            await asyncio.sleep(0.05)


async def wait_until_up(process: asyncio.subprocess.Process) -> None:
    """Wait until the server says that it is up, and a little longer, until Robot Framework handles its signals."""
    assert process.stderr is not None
    while True:
        line = await asyncio.wait_for(process.stderr.readline(), TIMEOUT)
        assert line, "the server ended before it was up"
        if b"up and running" in line:
            break
    await asyncio.sleep(0.5)


async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, message: str) -> str:
    """Import ``StdioEchoLib`` over the connection and call ``Echo``; return its result and close the connection."""
    peer = JsonRpcPeer(reader, writer)
    peer.start()
    try:
        await asyncio.wait_for(
            peer.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams()), TIMEOUT
        )
        await peer.send_notification(INITIALIZED_NOTIFICATION, InitializedParams())
        imported = await asyncio.wait_for(
            peer.send_request_typed(
                ImportLibraryResult, IMPORT_LIBRARY_REQUEST, ImportLibraryParams(name="StdioEchoLib")
            ),
            TIMEOUT,
        )
        params = RunKeywordParams(library_token=imported.token, name="Echo", args=[message])
        result = await asyncio.wait_for(peer.send_request_typed(RunKeywordResult, RUN_KEYWORD_REQUEST, params), TIMEOUT)
    finally:
        await peer.stop()
    return str(result.result)


async def end(process: asyncio.subprocess.Process) -> str:
    """Kill the server if it still runs; return what it wrote to its stderr."""
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.kill()
    assert process.stderr is not None
    stderr = await asyncio.wait_for(process.stderr.read(), TIMEOUT)
    await asyncio.wait_for(process.wait(), TIMEOUT)
    return stderr.decode(errors="replace")
