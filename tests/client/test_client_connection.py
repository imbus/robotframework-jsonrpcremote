"""Unit tests for the JsonRpcRemote client's transport selection (the stdio happy path
is covered end-to-end by atests/stdio/echo.robot)."""

import asyncio
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from typing import NoReturn

import pytest
from fake_server import FakeServer

from JsonRpcRemote import JsonRpcRemote, _Session, _split_command, _uri_from_list

_ATESTS_LIBRARIES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "atests", "libraries"))
_MINIMAL_SERVER = Path(__file__).resolve().parent.parent / "minimal_stdio_server.py"
_MINIMAL_PIPE_SERVER = Path(__file__).resolve().parent.parent / "minimal_pipe_server.py"
_NOT_ON_WINDOWS = pytest.mark.skipif(sys.platform == "win32", reason="socket files exist only off Windows")


def _make_session(uri: str, timeout: float = 5.0) -> _Session:
    return _Session(uri, None, None, None, timeout)


def _stdio_server_command(library: str) -> str:
    # Quoted, so that a path with a space survives the split of the client.
    return shlex.join(
        [sys.executable, "-m", "robot_jsonrpcremote_server", "--stdio", "--pythonpath", _ATESTS_LIBRARIES, library]
    )


if sys.platform == "win32":
    import _winapi

    def _pid_exists(pid: int) -> bool:
        """Whether the process still runs; os.kill(pid, 0) would send it a Ctrl+C or end it on Windows."""
        try:
            handle = _winapi.OpenProcess(_winapi.SYNCHRONIZE, False, pid)
        except OSError:
            return False
        try:
            # A process that has ended can still be opened while someone has a handle to it.
            return _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
        finally:
            _winapi.CloseHandle(handle)

else:

    def _pid_exists(pid: int) -> bool:
        """Whether the process still runs."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True


def _wait_pid_gone(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.05)
    return False


async def test_create_connection_rejects_unknown_scheme() -> None:
    session = _make_session("http://127.0.0.1:8271")
    with pytest.raises(
        ValueError, match="Unsupported URI scheme 'http'; supported schemes are 'tcp', 'pipe' and 'stdio'"
    ):
        await session.create_connection()


async def test_a_stdio_uri_with_two_slashes_is_refused_without_starting_a_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def start(*command: str, **options: object) -> NoReturn:
        pytest.fail(f"the client started {command}")

    monkeypatch.setattr("JsonRpcRemote.create_stdio_subprocess", start)
    session = _make_session("stdio://robot-jsonrpcremote-server --stdio MyLibrary")

    with pytest.raises(ValueError, match=re.escape("write 'stdio:robot-jsonrpcremote-server --stdio MyLibrary'")):
        await session.create_connection()


async def test_stdio_uri_requires_a_command() -> None:
    session = _make_session("stdio:")
    with pytest.raises(ValueError, match="must include a server command"):
        await session.create_connection()


async def test_stdio_uri_spawns_process_and_returns_streams() -> None:
    command = shlex.join([sys.executable, "-c", "import sys; sys.stdin.read()"])
    session = _make_session(f"stdio:{command}")

    reader, writer = await session.create_connection()
    try:
        assert isinstance(reader, asyncio.StreamReader)
        assert session._res.process is not None
        assert session._res.process.returncode is None
    finally:
        process = session._res.process
        assert process is not None
        process.kill()
        await process.wait()
        # To the end, so that the reader has closed its pipe before the event loop ends.
        await asyncio.wait_for(reader.read(), 10)
        writer.close()


@pytest.mark.skipif(sys.platform != "win32", reason="overlapped pipes exist only on Windows")
async def test_a_stdio_server_gets_overlapped_pipes() -> None:
    # So that a Python server can use I/O completion ports, without a thread per direction.
    code = (
        "import msvcrt, sys; from jsonrpcpeer._win32_pipes import is_overlapped; "
        "print(is_overlapped(msvcrt.get_osfhandle(0)), is_overlapped(msvcrt.get_osfhandle(1)), end='')"
    )
    session = _make_session(f"stdio:{shlex.join([sys.executable, '-c', code])}")

    reader, writer = await session.create_connection()
    try:
        kinds = await asyncio.wait_for(reader.read(), 10)
    finally:
        writer.close()
        process = session._res.process
        assert process is not None
        await asyncio.wait_for(process.wait(), 10)

    assert kinds == b"True True"


async def test_stdio_bad_command_raises_os_error() -> None:
    session = _make_session("stdio:definitely-not-a-real-server-binary-xyz --stdio Lib")
    with pytest.raises(FileNotFoundError):
        await session.create_connection()


def test_stdio_session_spawns_and_reaps_server() -> None:
    session = _Session(f"stdio:{_stdio_server_command('StdioEchoLib')}", "StdioEchoLib", (), None, 20.0)
    session.start()
    assert session.initialized.wait(20)
    assert session.start_error is None

    process = session._res.process
    assert process is not None
    pid = process.pid

    session.stop()

    assert process.returncode is not None
    assert _wait_pid_gone(pid), f"server subprocess {pid} still alive after teardown"


def test_cancelled_close_still_reaps_the_stdio_server(monkeypatch: pytest.MonkeyPatch) -> None:
    unhandled: list[threading.ExceptHookArgs] = []
    monkeypatch.setattr(threading, "excepthook", unhandled.append)
    session = _Session(f"stdio:{_stdio_server_command('StdioEchoLib')}", "StdioEchoLib", (), None, 20.0)
    session.start()
    assert session.initialized.wait(20)
    assert session.start_error is None

    async def cancelled_close() -> None:
        # As when another caller cancels the close future that all callers of wait_closed() share.
        raise asyncio.CancelledError

    monkeypatch.setattr(session.peer.writer, "wait_closed", cancelled_close)
    session.stop()

    assert session.process_returncode is not None
    assert unhandled == []


def test_failed_stdio_handshake_reaps_the_server_before_it_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    # The server only allows StdioEchoLib, so importing another library fails the handshake.
    session = _Session(f"stdio:{_stdio_server_command('StdioEchoLib')}", "NotAllowedLib", (), None, 20.0)
    pids: list[int] = []
    close_connection = session.close_connection

    async def remember_pid_and_close() -> None:
        if session._res.process is not None:
            pids.append(session._res.process.pid)
        await close_connection()

    monkeypatch.setattr(session, "close_connection", remember_pid_and_close)
    session.start()

    assert session.initialized.wait(20)
    assert "not available" in str(session.start_error)
    # Both hold as soon as the failure is reported, without waiting any longer.
    assert session.process_returncode is not None
    assert pids, "the spawned server was never released"
    assert not _pid_exists(pids[0])


class _FakeStartError(Exception):
    """Raised by the fake start of a server."""


@pytest.mark.parametrize("scheme", ["stdio", "pipe"])
@pytest.mark.parametrize(
    ("platform", "command", "argv"),
    [
        pytest.param(
            "win32",
            r"C:\path\to\python.exe -m robot_jsonrpcremote_server --stdio Lib",
            [r"C:\path\to\python.exe", "-m", "robot_jsonrpcremote_server", "--stdio", "Lib"],
            id="path_with_backslashes_on_windows",
        ),
        pytest.param(
            "win32",
            r'"C:\Program Files\tool\server.exe" --stdio',
            [r"C:\Program Files\tool\server.exe", "--stdio"],
            id="quoted_path_with_a_space_on_windows",
        ),
        pytest.param("linux", r"server my\ library", ["server", "my library"], id="backslash_on_posix"),
    ],
)
async def test_a_command_is_split_as_its_platform_writes_paths(
    monkeypatch: pytest.MonkeyPatch, platform: str, command: str, argv: list[str], scheme: str
) -> None:
    started: list[tuple[str, ...]] = []

    async def start(*command: str, **options: object) -> NoReturn:
        started.append(command)
        raise _FakeStartError

    monkeypatch.setattr(f"JsonRpcRemote.create_{scheme}_subprocess", start)
    monkeypatch.setattr(sys, "platform", platform)
    session = _make_session(f"{scheme}:{command}")

    with pytest.raises(_FakeStartError):
        await session.create_connection()

    assert started == [tuple(argv)]


@pytest.mark.skipif(sys.platform != "win32", reason="the event loop policies exist only on Windows")
def test_a_session_runs_when_a_library_has_set_the_selector_policy() -> None:
    # The policy holds for the whole process, so a process of its own sets it.
    script = textwrap.dedent("""
        import asyncio, sys
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        from JsonRpcRemote import JsonRpcRemote

        remote = JsonRpcRemote(sys.argv[1], "MinimalLibrary", rpc_timeout=10)
        try:
            print(asyncio.run(remote.run_keyword("Echo", ["through the proactor"], {})))
        finally:
            remote._stop_session()
    """)
    uri = f"stdio:{shlex.join([sys.executable, str(_MINIMAL_SERVER)])}"

    result = subprocess.run(
        [sys.executable, "-c", script, uri], capture_output=True, text=True, timeout=60, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "through the proactor"


def test_a_stdio_command_with_a_space_in_its_path_reaches_the_server(tmp_path: Path) -> None:
    # A small standalone server, as a server in another language would be started.
    directory = tmp_path / "with space"
    directory.mkdir()
    server = directory / _MINIMAL_SERVER.name
    shutil.copy(_MINIMAL_SERVER, server)
    remote = JsonRpcRemote(f"stdio:{shlex.join([sys.executable, str(server)])}", "MinimalLibrary", rpc_timeout=10)
    try:
        result = asyncio.run(remote.run_keyword("Echo", ["Grüße"], {}))
    finally:
        remote._stop_session()

    assert result == "Grüße"


# pipe:<command>


def _minimal_pipe_server_uri() -> str:
    return f"pipe:{shlex.join([sys.executable, str(_MINIMAL_PIPE_SERVER)])}"


def test_a_pipe_session_starts_and_reaps_its_server() -> None:
    session = _Session(_minimal_pipe_server_uri(), "MinimalLibrary", (), None, 20.0)
    session.start()
    assert session.initialized.wait(20)
    assert session.start_error is None

    process = session._res.process
    assert process is not None
    pid = process.pid

    session.stop()

    assert process.returncode is not None
    assert _wait_pid_gone(pid), f"server subprocess {pid} still alive after teardown"


async def test_a_pipe_command_that_cannot_be_found_names_the_command_and_the_uri_of_a_listening_server() -> None:
    session = _make_session("pipe:definitely-not-a-real-server-binary-xyz Lib")

    with pytest.raises(FileNotFoundError) as error:
        await session.create_connection()

    assert "'definitely-not-a-real-server-binary-xyz'" in str(error.value)
    assert "pipe://<name> connects to a server that listens on a pipe" in str(error.value)


async def test_pipe_uri_requires_a_command() -> None:
    session = _make_session("pipe:")
    with pytest.raises(ValueError, match=re.escape("'pipe:<command>'")):
        await session.create_connection()


def test_the_output_of_a_pipe_server_goes_to_the_stderr_of_the_client(capfd: pytest.CaptureFixture[str]) -> None:
    remote = JsonRpcRemote(_minimal_pipe_server_uri(), "MinimalLibrary", rpc_timeout=20)
    try:
        result = asyncio.run(remote.run_keyword("Echo", ["Grüße"], {}))
    finally:
        # Reaps the server, so its output is complete.
        remote._stop_session()
    out, err = capfd.readouterr()

    assert result == "Grüße"
    assert "minimal pipe server: a line from the server" in err
    assert "minimal pipe server: a line from its child" in err
    assert "minimal pipe server" not in out


# pipe://<name>


def test_a_pipe_uri_with_a_name_connects_to_a_server_that_listens_on_the_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with FakeServer(pipe=f"fake-server-{secrets.token_hex(8)}") as server:
        remote = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5)
        try:
            result = asyncio.run(remote.run_keyword("Echo", ["over a pipe"], {}))
        finally:
            remote._stop_session()

    assert result == "echo: over a pipe"


def test_the_import_from_a_pipe_that_nobody_listens_on_fails_with_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    name = f"fake-server-{secrets.token_hex(8)}"

    # The import connects.
    with pytest.raises(FileNotFoundError, match=name):
        JsonRpcRemote(f"pipe://{name}", "FakeLib", rpc_timeout=5)


@_NOT_ON_WINDOWS
def test_a_pipe_uri_with_an_absolute_path_connects_to_that_socket_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Short, unlike tmp_path, which can be too long for a socket path on macOS; and not the working directory.
    directory = tempfile.mkdtemp(prefix="jsonrpcremote-")
    monkeypatch.chdir(tmp_path)
    try:
        path = os.path.join(directory, "robot.sock")
        with FakeServer(pipe=path) as server:
            remote = JsonRpcRemote(f"pipe://{path}", "FakeLib", rpc_timeout=5)
            try:
                result = asyncio.run(remote.run_keyword("Echo", ["absolute"], {}))
            finally:
                remote._stop_session()
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    assert server.uri.startswith("pipe:///")
    assert result == "echo: absolute"


async def test_pipe_uri_requires_a_name() -> None:
    session = _make_session("pipe://")
    with pytest.raises(ValueError, match=re.escape("'pipe://<name>'")):
        await session.create_connection()


# uri as a list


@pytest.mark.parametrize(
    ("uri", "string"),
    [
        pytest.param(
            ["pipe:", "robot-jsonrpcremote-server", "--pythonpath", ".", "MyLibrary"],
            "pipe:robot-jsonrpcremote-server --pythonpath . MyLibrary",
            id="scheme_as_an_element_of_its_own",
        ),
        pytest.param(
            ["pipe:robot-jsonrpcremote-server", "--pythonpath", ".", "MyLibrary"],
            "pipe:robot-jsonrpcremote-server --pythonpath . MyLibrary",
            id="scheme_in_front_of_the_program",
        ),
        pytest.param(["PIPE:", "server"], "pipe:server", id="scheme_in_upper_case"),
        pytest.param(
            ["stdio:", "robot-jsonrpcremote-server", "--stdio", "MyLibrary"],
            "stdio:robot-jsonrpcremote-server --stdio MyLibrary",
            id="stdio",
        ),
        pytest.param(["pipe:", Path("server"), "--port", 8271], "pipe:server --port 8271", id="elements_no_strings"),
        pytest.param(["pipe:", "server", "my library"], "pipe:server 'my library'", id="argument_that_needs_quotes"),
        # Not pipe://server/..., which would be the name of a pipe.
        pytest.param(
            ["pipe:", "//server/share/tool.exe"], "pipe:'//server/share/tool.exe'", id="program_with_two_slashes"
        ),
    ],
)
def test_a_list_becomes_the_string_form_of_its_uri(uri: list[object], string: str) -> None:
    assert _uri_from_list(uri) == string


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(["server", "my library"], id="argument_with_a_space"),
        pytest.param(["//server/share/tool.exe", "it's"], id="program_with_two_slashes"),
    ],
)
def test_the_string_form_of_a_list_splits_into_the_same_command(command: list[str]) -> None:
    string = _uri_from_list(["pipe:", *command])

    assert _split_command(string.removeprefix("pipe:")) == command


@pytest.mark.parametrize(
    "uri",
    [
        pytest.param([], id="an_empty_list"),
        pytest.param(["pipe:"], id="the_scheme_alone"),
        pytest.param(["pipe://robot"], id="a_pipe_name"),
        pytest.param(["stdio://robot-jsonrpcremote-server", "--stdio"], id="stdio_with_two_slashes"),
        pytest.param(["tcp://127.0.0.1:8271"], id="tcp"),
        pytest.param(["robot-jsonrpcremote-server", "MyLibrary"], id="no_supported_scheme"),
    ],
)
def test_a_list_without_a_command_is_refused_and_starts_no_session(
    monkeypatch: pytest.MonkeyPatch, uri: list[str]
) -> None:
    started: list[_Session] = []
    monkeypatch.setattr(_Session, "start", lambda session: started.append(session))

    with pytest.raises(ValueError, match=re.escape("A list for uri must hold the command of a pipe: or stdio: URI")):
        JsonRpcRemote(uri, "MyLibrary", rpc_timeout=1)

    assert started == []


# The awkward arguments of the probe in the design of add-command-lists.
_AWKWARD_COMMAND = [
    r"C:\Program Files\tool\server.exe",
    "/opt/my tools/server",
    "my library",
    "it's",
    'say "hi"',
    "a\\b",
    "",
    "new\nline",
    "ümlaut",
]


@pytest.mark.parametrize("scheme", ["pipe", "stdio"])
@pytest.mark.parametrize("form", ["scheme_as_an_element_of_its_own", "scheme_in_front_of_the_program"])
@pytest.mark.parametrize("platform", ["win32", "linux"])
async def test_a_list_reaches_the_start_of_the_server_element_by_element(
    monkeypatch: pytest.MonkeyPatch, scheme: str, form: str, platform: str
) -> None:
    started: list[tuple[str, ...]] = []

    async def start(*command: str, **options: object) -> NoReturn:
        started.append(command)
        raise _FakeStartError

    monkeypatch.setattr(f"JsonRpcRemote.create_{scheme}_subprocess", start)
    monkeypatch.setattr(sys, "platform", platform)
    if form == "scheme_as_an_element_of_its_own":
        uri = [f"{scheme}:", *_AWKWARD_COMMAND]
    else:
        uri = [f"{scheme}:{_AWKWARD_COMMAND[0]}", *_AWKWARD_COMMAND[1:]]
    session = _make_session(_uri_from_list(uri))

    with pytest.raises(_FakeStartError):
        await session.create_connection()

    assert started == [tuple(_AWKWARD_COMMAND)]


def test_a_list_starts_a_server_from_a_folder_with_a_space_in_its_name(tmp_path: Path) -> None:
    # No quotes: the path is one element of the list.
    directory = tmp_path / "with space"
    directory.mkdir()
    for helper in (_MINIMAL_PIPE_SERVER, _MINIMAL_SERVER):
        shutil.copy(helper, directory / helper.name)
    server = directory / _MINIMAL_PIPE_SERVER.name
    remote = JsonRpcRemote(["pipe:", sys.executable, str(server)], "MinimalLibrary", rpc_timeout=20)
    try:
        result = asyncio.run(remote.run_keyword("Echo", ["Grüße"], {}))
    finally:
        remote._stop_session()

    assert result == "Grüße"
