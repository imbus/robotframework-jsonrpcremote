"""The connection over the stdin and stdout of a process, each scenario in a process of its own.

``open_stdio_connection()`` changes the file descriptors of its process, so it cannot run in the
process of the tests: pytest's capture and every later test would break.

On Windows, the scenarios run on two kinds of pipes: the overlapped pipes of
``create_stdio_subprocess()``, as the client creates them, and the synchronous pipes of
``subprocess``, as other parents such as VS Code create them.
"""

import asyncio
import ctypes
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import pytest

from jsonrpcpeer import JsonRpcPeer, create_stdio_subprocess

if sys.platform == "win32":
    import _winapi
    import msvcrt
    from asyncio import windows_utils

    def _handle_count() -> int:
        """The number of handles that this process has open."""
        count = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetProcessHandleCount(ctypes.c_void_p(-1), ctypes.byref(count)):
            raise ctypes.WinError()
        return count.value


_WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="this behavior exists only on Windows")
# On Windows, subprocess cannot start a process without a standard handle: it puts in the parent's handle.
_NEEDS_A_CLOSED_STREAM = pytest.mark.skipif(sys.platform == "win32", reason="the test closes a stream with /bin/sh")

# Shared by every script: the process writes what it has to say to the writer, or to stderr.
_PRELUDE = """\
import asyncio, json, os, shlex, subprocess, sys, time
from jsonrpcpeer import open_stdio_connection

async def flush_and_close(writer):
    await writer.drain()
    while writer.transport.get_write_buffer_size():
        await asyncio.sleep(0.01)
    writer.close()
"""

_STDIN_NEEDED = "stdio mode needs a stdin that can be watched for input, such as a pipe"

_PIPES = ["overlapped", "synchronous"] if sys.platform == "win32" else ["pipes"]


@pytest.fixture(params=_PIPES)
def pipes(request: pytest.FixtureRequest) -> str:
    """The pipes of the process: on Windows overlapped or synchronous ones, elsewhere ordinary ones."""
    return str(request.param)


def _script(body: str) -> str:
    return _PRELUDE + textwrap.dedent(body)


def _python(closing: str = "") -> list[str]:
    """The command that starts Python; ``closing`` closes standard streams before, such as ``2>&-``."""
    if not closing:
        return [sys.executable]
    return ["/bin/sh", "-c", f'exec "$0" "$@" {closing}', sys.executable]


def _run_without_stderr(body: str, data: bytes) -> tuple[bytes, int]:
    """Run ``body`` in a process that starts with file descriptor 2 closed; return its stdout and exit code."""
    result = subprocess.run(
        [*_python("2>&-"), "-c", _script(body)],
        input=data,
        stdout=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return result.stdout, result.returncode


@dataclass
class _Child:
    process: asyncio.subprocess.Process
    reader: asyncio.StreamReader
    """For the stdout of the process."""
    writer: asyncio.StreamWriter
    """For the stdin of the process."""

    @property
    def stderr(self) -> asyncio.StreamReader:
        assert self.process.stderr is not None
        return self.process.stderr


@asynccontextmanager
async def _process(pipes: str, body: str, stderr: int = asyncio.subprocess.PIPE) -> AsyncIterator[_Child]:
    """A process that runs ``body`` on ``pipes``; it is killed if it is still running at the end."""
    argv = (sys.executable, "-c", _script(body))
    if pipes == "synchronous":
        process = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=stderr
        )
        assert process.stdout is not None
        assert process.stdin is not None
        child = _Child(process, process.stdout, process.stdin)
    else:
        child = _Child(*await create_stdio_subprocess(*argv, stderr=stderr))
    try:
        yield child
    finally:
        child.writer.close()
        if child.process.returncode is None:
            with suppress(ProcessLookupError):
                child.process.kill()
        await child.process.wait()
        # To the end, so that the reader of the pair has closed its pipe before the event loop ends:
        # on Windows, process.wait() does not wait for the pipes of create_stdio_subprocess().
        with suppress(Exception):
            await asyncio.wait_for(child.reader.read(), 10)


async def _run(pipes: str, body: str, data: bytes = b"") -> tuple[bytes, str, int]:
    """Run ``body`` and send it ``data``; return its stdout, stderr and exit code once it has ended.

    Its stdin stays open until then.
    """
    async with _process(pipes, body) as child:
        child.writer.write(data)
        stdout, stderr, _ = await asyncio.wait_for(
            asyncio.gather(child.reader.read(), child.stderr.read(), child.writer.drain()), 30
        )
        code = await asyncio.wait_for(child.process.wait(), 10)
    return stdout, stderr.decode(errors="replace"), code


@dataclass
class _OwnPipes:
    process: asyncio.subprocess.Process
    reader: asyncio.StreamReader
    read_transport: asyncio.ReadTransport
    write_transport: asyncio.WriteTransport

    @property
    def stderr(self) -> asyncio.StreamReader:
        assert self.process.stderr is not None
        return self.process.stderr


@asynccontextmanager
async def _process_on_own_pipes(
    body: str,
    *options: str,
    overlapped: tuple[bool, bool] = (True, True),
    hand_down: bool = False,
    stderr: int = asyncio.subprocess.PIPE,
) -> AsyncIterator[_OwnPipes]:
    """A process on pipes that the test makes itself, so that it can close the end that it reads.

    ``overlapped`` says for the stdin and the stdout of the process whether they are overlapped
    pipes on Windows. With ``hand_down``, the process also inherits further handles to its ends of
    the pipes on Windows, as CPython's launcher of a venv hands down the originals of the standard handles.
    """
    our_read: object
    our_write: object
    handed_down: list[int] = []
    if sys.platform == "win32":
        stdin_overlapped, stdout_overlapped = overlapped
        # Our ends are overlapped, as the proactor needs them.
        child_stdin, our_stdin = windows_utils.pipe(overlapped=(stdin_overlapped, True), duplex=True)
        our_stdout, child_stdout = windows_utils.pipe(overlapped=(True, stdout_overlapped), duplex=True)
        if hand_down:
            current = _winapi.GetCurrentProcess()
            handed_down = [
                _winapi.DuplicateHandle(current, end, current, 0, True, _winapi.DUPLICATE_SAME_ACCESS)
                for end in (child_stdin, child_stdout)
            ]
        stdin_fd = msvcrt.open_osfhandle(child_stdin, os.O_RDONLY)
        stdout_fd = msvcrt.open_osfhandle(child_stdout, 0)
        our_read = windows_utils.PipeHandle(our_stdout)
        our_write = windows_utils.PipeHandle(our_stdin)
    else:
        stdin_fd, write_fd = os.pipe()
        read_fd, stdout_fd = os.pipe()
        our_read = os.fdopen(read_fd, "rb", 0)
        our_write = os.fdopen(write_fd, "wb", 0)
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            *options,
            "-c",
            _script(body),
            stdin=stdin_fd,
            stdout=stdout_fd,
            stderr=stderr,
            # So that the process inherits the handles to hand down, with the others of this process.
            close_fds=not handed_down,
        )
    finally:
        os.close(stdin_fd)
        os.close(stdout_fd)
        if sys.platform == "win32":
            for handle in handed_down:
                _winapi.CloseHandle(handle)
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    read_transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), our_read)
    write_transport, _ = await loop.connect_write_pipe(asyncio.Protocol, our_write)
    try:
        yield _OwnPipes(process, reader, read_transport, write_transport)
    finally:
        read_transport.close()
        write_transport.close()
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        await process.wait()


def _overlapped(pipes: str) -> tuple[bool, bool]:
    return (True, True) if pipes == "overlapped" else (False, False)


async def _run_after_the_input_ended(pipes: str, body: str, data: bytes = b"") -> tuple[bytes, str, int]:
    """Run ``body``, send it ``data`` and close its stdin; return its stdout, stderr and exit code."""
    async with _process(pipes, body) as child:
        child.writer.write(data)
        child.writer.close()
        stdout, stderr = await asyncio.wait_for(asyncio.gather(child.reader.read(), child.stderr.read()), 30)
        code = await asyncio.wait_for(child.process.wait(), 10)
    return stdout, stderr.decode(errors="replace"), code


_REFUSED = """
    async def main():
        try:
            await open_stdio_connection()
        except RuntimeError as error:
            if sys.stdout is not None:
                print("still on stdout", flush=True)
                os.write(1, b"still on file descriptor 1\\n")
            sys.stderr.write(f"RuntimeError: {error}\\n")
            raise SystemExit(1)

    asyncio.run(main())
"""


def _run_refused(stdin: int | IO[str], closing: str = "") -> subprocess.CompletedProcess[str]:
    """Run a process whose call is refused; after the refusal, it writes to its stdout."""
    return subprocess.run(
        [*_python(closing), "-c", _script(_REFUSED)],
        stdin=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


_ECHO_PEER = """
    from jsonrpcpeer import JsonRpcPeer

    async def echo(params: dict[str, str]) -> dict[str, str]:
        return params

    async def main():
        peer = JsonRpcPeer(*await open_stdio_connection())
        peer.register_request_handler("echo", echo)
        await peer.run()

    asyncio.run(main())
"""


async def test_a_peer_on_the_pair_answers_a_request(pipes: str) -> None:
    # Started by create_stdio_subprocess(), except on the synchronous pipes of Windows.
    async with _process(pipes, _ECHO_PEER) as child:
        peer = JsonRpcPeer(child.reader, child.writer)
        peer.start()
        result = await asyncio.wait_for(peer.send_request("echo", {"text": "Grüße"}), 10)
        # Closing our end ends the input of the process, and its peer ends.
        await peer.stop()
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert result == {"text": "Grüße"}
    assert code == 0


async def test_large_messages_pass_unchanged(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            size = int(await reader.readline())
            writer.write(await reader.readexactly(size))
            await flush_and_close(writer)

        asyncio.run(main())
    """
    payload = os.urandom(4 * 1024 * 1024)

    stdout, stderr, code = await _run(pipes, body, b"%d\n" % len(payload) + payload)

    assert code == 0, stderr
    assert stdout == payload


async def test_print_appears_on_stderr_at_the_end_of_its_line(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            print("print-marker")
            await reader.readline()
            writer.write(b"done")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    async with _process(pipes, body) as child:
        # The process waits for our line, so it still runs when its line arrives.
        line = await asyncio.wait_for(child.stderr.readline(), 10)
        child.writer.write(b"go\n")
        stdout = await asyncio.wait_for(child.reader.read(), 10)

    assert line.rstrip(b"\r\n") == b"print-marker"
    assert stdout == b"done"


async def test_direct_writes_to_file_descriptor_1_appear_on_stderr(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            os.write(1, b"file-descriptor-marker\\n")
            sys.__stdout__.write("dunder-stdout-marker\\n")
            sys.__stdout__.flush()
            writer.write(b"done")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(pipes, body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "file-descriptor-marker" in stderr
    assert "dunder-stdout-marker" in stderr


async def test_output_of_child_processes_appears_on_stderr(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            subprocess.run([sys.executable, "-c", "print('subprocess-marker')"], check=True, timeout=20)
            command = [sys.executable, "-c", "print('os-system-marker')"]
            # cmd.exe does not understand the quotes of a POSIX shell.
            os.system(subprocess.list2cmdline(command) if sys.platform == "win32" else shlex.join(command))
            writer.write(b"done")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(pipes, body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "subprocess-marker" in stderr
    assert "os-system-marker" in stderr


async def test_text_buffered_before_the_call_appears_on_stderr(pipes: str) -> None:
    body = """
        # stdout is a pipe, so this stays in the buffer of sys.stdout.
        sys.stdout.write("buffered-marker\\n")

        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"done")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(pipes, body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "buffered-marker" in stderr


async def test_print_after_the_connection_has_closed_appears_on_stderr(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"done")
            await flush_and_close(writer)
            await asyncio.sleep(0.1)
            print("after-close-marker", flush=True)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(pipes, body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "after-close-marker" in stderr
    assert "Traceback" not in stderr


async def _send_once_the_process_is_ready(pipes: str, body: str) -> tuple[bytes, str, int]:
    """Run ``body``, which writes a line when it is ready and then waits; send it the data of the connection."""
    async with _process(pipes, body) as child:
        assert await asyncio.wait_for(child.reader.readline(), 10) == b"ready\n"
        # The process does not run its event loop now, so the data waits on its stdin.
        child.writer.write(b"protocol-bytes\n")
        stdout, stderr = await asyncio.wait_for(asyncio.gather(child.reader.read(), child.stderr.read()), 30)
        code = await asyncio.wait_for(child.process.wait(), 10)
    return stdout, stderr.decode(errors="replace"), code


async def test_reading_stdin_in_the_process_gets_nothing_of_the_connection(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"ready\\n")
            time.sleep(1)
            results = {}
            try:
                results["input"] = input()
            except EOFError:
                results["input"] = "EOFError"
            results["sys.stdin"] = sys.stdin.read()
            results["os.read"] = os.read(0, 100).decode()
            results["reader"] = (await reader.readline()).decode()
            writer.write(json.dumps(results).encode())
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _send_once_the_process_is_ready(pipes, body)

    assert code == 0, stderr
    assert json.loads(stdout) == {
        "input": "EOFError",
        "sys.stdin": "",
        "os.read": "",
        "reader": "protocol-bytes\n",
    }


async def test_a_child_process_that_reads_stdin_sees_its_end_at_once(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"ready\\n")
            time.sleep(1)
            started = time.monotonic()
            code = "import sys; print(repr(sys.stdin.buffer.read(14)))"
            child = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
            results = {"child": child.stdout.strip(), "seconds": time.monotonic() - started}
            results["reader"] = (await reader.readline()).decode()
            writer.write(json.dumps(results).encode())
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _send_once_the_process_is_ready(pipes, body)

    assert code == 0, stderr
    results = json.loads(stdout)
    assert results["child"] == "b''"
    assert results["seconds"] < 5
    assert results["reader"] == "protocol-bytes\n"


_LEAVES_A_CHILD_RUNNING = """
    async def main():
        reader, writer = await open_stdio_connection()
        # close_fds=False: the child inherits every file descriptor that is inheritable.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(15)"], close_fds=False)
        writer.write(b"%d\\n" % child.pid)
        await writer.drain()
        while writer.transport.get_write_buffer_size():
            await asyncio.sleep(0.01)
        os._exit(3)

    asyncio.run(main())
"""


async def test_a_child_process_does_not_keep_the_connection_open(pipes: str) -> None:
    # The child process would inherit a pipe on stderr, which would keep it open too.
    async with _process(pipes, _LEAVES_A_CHILD_RUNNING, stderr=asyncio.subprocess.DEVNULL) as child:
        child_pid = int(await asyncio.wait_for(child.reader.readline(), 10))
        started = time.monotonic()
        try:
            rest = await asyncio.wait_for(child.reader.read(), 12)
            seconds = time.monotonic() - started
        finally:
            # On Windows, a process that has gone gives an OSError of its own.
            with suppress(OSError):
                os.kill(child_pid, signal.SIGTERM)
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert rest == b""
    assert seconds < 10
    assert code == 3


@_WINDOWS_ONLY
async def test_handles_to_the_pipes_that_a_launcher_handed_down_do_not_keep_the_connection_open(pipes: str) -> None:
    async with _process_on_own_pipes(
        _LEAVES_A_CHILD_RUNNING, overlapped=_overlapped(pipes), hand_down=True, stderr=asyncio.subprocess.DEVNULL
    ) as child:
        child_pid = int(await asyncio.wait_for(child.reader.readline(), 10))
        started = time.monotonic()
        try:
            rest = await asyncio.wait_for(child.reader.read(), 12)
            seconds = time.monotonic() - started
        finally:
            with suppress(OSError):
                os.kill(child_pid, signal.SIGTERM)
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert rest == b""
    assert seconds < 10
    assert code == 3


def test_stdin_that_is_the_null_device_is_refused_and_the_streams_stay() -> None:
    with open(os.devnull) as null:
        result = _run_refused(null)

    assert result.returncode == 1
    assert f"{_STDIN_NEEDED}, but stdin is a character device such as {os.devnull}" in result.stderr
    assert result.stdout == "still on stdout\nstill on file descriptor 1\n"


def test_stdin_that_is_a_regular_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "stdin.txt"
    path.write_text("")
    with path.open() as file:
        result = _run_refused(file)

    assert result.returncode == 1
    assert f"{_STDIN_NEEDED}, but stdin is a regular file" in result.stderr


@_NEEDS_A_CLOSED_STREAM
def test_a_closed_stdin_is_refused() -> None:
    result = _run_refused(subprocess.PIPE, closing="0<&-")

    assert result.returncode == 1
    assert f"{_STDIN_NEEDED}, but stdin is closed" in result.stderr


@_NEEDS_A_CLOSED_STREAM
def test_a_closed_stdout_is_refused() -> None:
    result = _run_refused(subprocess.PIPE, closing="1>&-")

    assert result.returncode == 1
    assert "stdio mode needs an open stdout, but stdout is closed" in result.stderr


async def test_a_pipe_whose_writing_end_is_closed_is_a_valid_stdin(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"read %r" % await reader.read())
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run_after_the_input_ended(pipes, body)

    assert code == 0, stderr
    assert stdout == b"read b''"


_WITHOUT_STDERR = """
    async def main():
        {close}
        reader, writer = await open_stdio_connection()
        print("print-to-nowhere", flush=True)
        os.write(1, b"file-descriptor-1-to-nowhere\\n")
        with contextlib.suppress(OSError):
            os.write(2, b"file-descriptor-2-to-nowhere\\n")
        writer.write(b"echo " + await reader.readline())
        await flush_and_close(writer)

    import contextlib
    asyncio.run(main())
"""


@_NEEDS_A_CLOSED_STREAM
def test_a_process_that_starts_without_a_stderr_keeps_the_connection_clean() -> None:
    # The selector of the event loop then gets file descriptor 2.
    stdout, code = _run_without_stderr(_WITHOUT_STDERR.format(close="pass"), b"line\n")

    assert code == 0
    assert stdout == b"echo line\n"


async def test_a_stderr_closed_before_the_call_keeps_the_connection_clean(pipes: str) -> None:
    # The process started with a stderr, so file descriptor 2 is free when the function runs.
    stdout, _, code = await _run(pipes, _WITHOUT_STDERR.format(close="os.close(2)"), b"line\n")

    assert code == 0
    assert stdout == b"echo line\n"


async def test_closing_the_writer_ends_the_connection_in_both_directions(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"hello")
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 5)
            rest = await asyncio.wait_for(reader.read(), 5)
            sys.stderr.write(f"reader got {rest!r}\\n")

        asyncio.run(main())
    """
    async with _process(pipes, body) as child:
        # Our end of its stdin stays open: the reader ends because the writer was closed.
        stdout = await asyncio.wait_for(child.reader.read(), 10)
        stderr = (await asyncio.wait_for(child.stderr.read(), 10)).decode(errors="replace")
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert code == 0, stderr
    assert stdout == b"hello"
    assert "reader got b''" in stderr


async def test_the_writer_stays_usable_when_the_input_ends(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            data = await asyncio.wait_for(reader.read(), 5)
            writer.write(b"bye " + data)
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 5)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run_after_the_input_ended(pipes, body, b"data")

    assert code == 0, stderr
    assert stdout == b"bye data"


async def test_the_other_end_going_away_ends_the_connection_without_unretrieved_errors(pipes: str) -> None:
    body = """
        import gc

        async def main():
            reader, writer = await open_stdio_connection()
            error = None
            try:
                for _ in range(4000):
                    writer.write(b"x" * 65536)
                    await asyncio.wait_for(writer.drain(), 10)
            except Exception as exc:
                error = exc
            rest = await asyncio.wait_for(reader.read(), 5)
            # Without awaiting wait_closed(), which would retrieve the error itself.
            del reader, writer
            gc.collect()
            await asyncio.sleep(0.1)
            gc.collect()
            sys.stderr.write(f"connection error {isinstance(error, ConnectionError)}, reader got {rest!r}\\n")

        asyncio.run(main())
    """
    # Our end of its stdin stays open until the end: the reader must end because stdout went away.
    async with _process_on_own_pipes(body, "-X", "dev", overlapped=_overlapped(pipes)) as child:
        await asyncio.wait_for(child.reader.read(1024), 10)
        child.read_transport.close()
        stderr = (await asyncio.wait_for(child.stderr.read(), 30)).decode(errors="replace")
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert code == 0, stderr
    assert "connection error True, reader got b''" in stderr
    for report in ("never retrieved", "ResourceWarning", "unclosed"):
        assert report not in stderr


def test_a_process_on_the_default_pipes_of_node_answers_a_request() -> None:
    # Node starts a process as VS Code starts a debug adapter, with synchronous pipes on Windows.
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is not installed, and CI runners have it")
        pytest.skip("node is not installed")
    script = Path(__file__).with_name("node_default_pipes.js")

    result = subprocess.run(
        [node, str(script), sys.executable, "-c", _script(_ECHO_PEER)],
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    response = json.loads(result.stdout)
    assert response["id"] == 1
    assert response["result"] == {"text": "Grüße"}


# create_stdio_subprocess()


async def test_a_process_with_plain_blocking_reads_and_writes_gets_all_bytes() -> None:
    # One reader and one writer, without open_stdio_connection(), as a server in another language would.
    code = textwrap.dedent("""
        import sys
        size = int(sys.stdin.buffer.readline())
        sys.stdout.buffer.write(sys.stdin.buffer.read(size))
        sys.stdout.buffer.flush()
    """)
    payload = os.urandom(4 * 1024 * 1024)
    process, reader, writer = await create_stdio_subprocess(sys.executable, "-c", code)
    try:
        writer.write(b"%d\n" % len(payload) + payload)
        echoed, _ = await asyncio.wait_for(asyncio.gather(reader.read(), writer.drain()), 30)
        returncode = await asyncio.wait_for(process.wait(), 10)
    finally:
        writer.close()
        if process.returncode is None:
            process.kill()
            await process.wait()

    assert returncode == 0
    assert echoed == payload


async def test_further_arguments_reach_the_start_of_the_process(tmp_path: Path) -> None:
    code = "import os, sys; sys.stderr.write(os.getcwd()); sys.stdout.write('done')"
    process, reader, writer = await create_stdio_subprocess(
        sys.executable, "-c", code, stderr=asyncio.subprocess.PIPE, cwd=tmp_path
    )
    assert process.stderr is not None
    try:
        stdout, stderr = await asyncio.wait_for(asyncio.gather(reader.read(), process.stderr.read()), 30)
        returncode = await asyncio.wait_for(process.wait(), 10)
    finally:
        writer.close()

    assert returncode == 0
    assert Path(stderr.decode()).samefile(tmp_path)
    assert stdout == b"done"


async def test_closing_the_writer_ends_the_input_of_the_process() -> None:
    code = "import sys; data = sys.stdin.buffer.read(); sys.stderr.write(f'read {data!r}')"
    process, reader, writer = await create_stdio_subprocess(sys.executable, "-c", code, stderr=asyncio.subprocess.PIPE)
    assert process.stderr is not None
    writer.write(b"data")
    writer.close()
    stderr = await asyncio.wait_for(process.stderr.read(), 30)
    returncode = await asyncio.wait_for(process.wait(), 10)
    # At the latest now that the process has ended, the reader sees the end of the stream.
    rest = await asyncio.wait_for(reader.read(), 5)

    assert returncode == 0
    assert stderr == b"read b'data'"
    assert rest == b""


async def test_the_caller_reads_all_output_that_the_process_wrote_before_it_ended() -> None:
    # Many small writes, and the process ends while the reader of the caller is paused with more than
    # 128 KiB unread. Several rounds, because whether the end comes during a pause is a matter of timing.
    code = "import os\nfor _ in range(140):\n    os.write(1, b'x' * 1000)\n"
    for _ in range(5):
        process, reader, writer = await create_stdio_subprocess(sys.executable, "-c", code)
        try:
            # Not process.wait(), which on POSIX also waits until the caller has read the pipe.
            deadline = time.monotonic() + 10
            while process.returncode is None and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            output = await asyncio.wait_for(reader.read(), 10)
        finally:
            writer.close()
            await asyncio.wait_for(process.wait(), 10)

        assert len(output) == 140 * 1000


async def test_a_command_that_cannot_be_started_raises_file_not_found_error() -> None:
    if sys.platform == "win32":
        handles = _handle_count()

    for _ in range(20):
        with pytest.raises(FileNotFoundError):
            await create_stdio_subprocess("jsonrpcpeer-test-no-such-command")

    if sys.platform == "win32":
        # A failed start that kept the parent's ends of the pipes would leave two handles each time.
        assert _handle_count() - handles < 10


class _FakeStartError(Exception):
    """Raised by the fake start of a process."""


@_WINDOWS_ONLY
@pytest.mark.parametrize(
    ("console", "options", "expected"),
    [
        pytest.param(False, {}, "CREATE_NO_WINDOW", id="without_console"),
        pytest.param(True, {}, None, id="with_console"),
        pytest.param(
            False, {"creationflags": "CREATE_NEW_PROCESS_GROUP"}, "CREATE_NEW_PROCESS_GROUP", id="given_flags"
        ),
    ],
)
async def test_a_process_gets_no_window_only_if_the_caller_has_no_console(
    monkeypatch: pytest.MonkeyPatch, console: bool, options: dict[str, str], expected: str | None
) -> None:
    from jsonrpcpeer import _win32_pipes

    seen: dict[str, object] = {}

    async def start(*argv: object, **kwargs: object) -> None:
        seen.update(kwargs)
        raise _FakeStartError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    monkeypatch.setattr(_win32_pipes, "has_console", lambda: console)
    # The flags exist only on Windows, so they are named here, for the type check on other platforms.
    flags = {name: getattr(subprocess, value) for name, value in options.items()}

    with pytest.raises(_FakeStartError):
        await create_stdio_subprocess(sys.executable, **flags)

    assert seen.get("creationflags") == (None if expected is None else getattr(subprocess, expected))


@_WINDOWS_ONLY
def test_a_console_without_a_window_counts_as_a_console() -> None:
    # As the console of a process that its parent started with CREATE_NO_WINDOW, which a child can share.
    code = "from jsonrpcpeer._win32_pipes import has_console; print(has_console())"

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
        # The flag exists only on Windows, so it is named here, for the type check on other platforms.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW"),
    )

    assert result.stdout.strip() == "True"


# Windows: I/O completion ports, threads and the standard handles


@_WINDOWS_ONLY
async def test_the_streams_take_a_thread_only_for_synchronous_pipes(pipes: str) -> None:
    body = """
        import threading

        async def main():
            before = threading.active_count()
            reader, writer = await open_stdio_connection()
            size = int(await reader.readline())
            data = await reader.readexactly(size)
            writer.write(b"%d\\n" % (threading.active_count() - before) + data)
            await flush_and_close(writer)

        asyncio.run(main())
    """
    payload = os.urandom(4 * 1024 * 1024)

    stdout, stderr, code = await _run(pipes, body, b"%d\n" % len(payload) + payload)

    threads, _, echoed = stdout.partition(b"\n")
    assert code == 0, stderr
    assert echoed == payload
    assert int(threads) == (2 if pipes == "synchronous" else 0)


@_WINDOWS_ONLY
async def test_a_synchronous_stdin_with_an_overlapped_stdout_takes_one_thread() -> None:
    body = """
        import threading

        async def main():
            before = threading.active_count()
            reader, writer = await open_stdio_connection()
            line = await reader.readline()
            writer.write(b"%d threads, echo %s" % (threading.active_count() - before, line))
            await flush_and_close(writer)

        asyncio.run(main())
    """
    async with _process_on_own_pipes(body, overlapped=(False, True)) as child:
        child.write_transport.write(b"hello\n")
        stdout, stderr = await asyncio.wait_for(asyncio.gather(child.reader.read(), child.stderr.read()), 30)
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert code == 0, stderr.decode(errors="replace")
    assert stdout == b"1 threads, echo hello\n"


@_WINDOWS_ONLY
async def test_a_slow_reader_at_the_other_end_does_not_hold_up_the_event_loop() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"ready\\n")
            await writer.drain()
            loop = asyncio.get_running_loop()
            due = loop.time() + 0.5
            ran = loop.create_future()
            loop.call_at(due, lambda: ran.set_result(loop.time() - due))
            writer.write(bytes(range(256)) * 16384)
            started = loop.time()
            await writer.drain()
            drained = loop.time() - started
            sys.stderr.write(f"late by {await ran:.3f} s, drained after {drained:.3f} s\\n")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    async with _process("synchronous", body) as child:
        assert await asyncio.wait_for(child.reader.readline(), 10) == b"ready\n"
        # Our end stops reading once its buffer is full, so the pipe fills up.
        await asyncio.sleep(2)
        data, stderr_bytes = await asyncio.wait_for(asyncio.gather(child.reader.read(), child.stderr.read()), 30)
        code = await asyncio.wait_for(child.process.wait(), 10)
    stderr = stderr_bytes.decode(errors="replace")

    assert code == 0, stderr
    assert data == bytes(range(256)) * 16384
    times = re.search(r"late by ([\d.]+) s, drained after ([\d.]+) s", stderr)
    assert times is not None, stderr
    assert float(times[1]) < 1
    # drain() waits until the other end has read most of it.
    assert float(times[2]) > 1


@_WINDOWS_ONLY
async def test_closing_the_writer_ends_both_threads() -> None:
    body = """
        import threading

        async def main():
            before = threading.active_count()
            reader, writer = await open_stdio_connection()
            started = time.monotonic()
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 5)
            rest = await asyncio.wait_for(reader.read(), 5)
            while threading.active_count() > before and time.monotonic() - started < 5:
                await asyncio.sleep(0.01)
            seconds = time.monotonic() - started
            left = threading.active_count() - before
            sys.stderr.write(f"reader got {rest!r}, {left} threads left after {seconds:.3f} s\\n")

        asyncio.run(main())
    """
    async with _process("synchronous", body) as child:
        # Our end of its stdin stays open, and we send nothing.
        stderr = (await asyncio.wait_for(child.stderr.read(), 30)).decode(errors="replace")
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert code == 0, stderr
    ended = re.search(r"reader got b'', 0 threads left after ([\d.]+) s", stderr)
    assert ended is not None, stderr
    assert float(ended[1]) < 1


@_WINDOWS_ONLY
async def test_a_child_process_does_not_wait_for_the_next_message() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"ready\\n")
            await writer.drain()
            # Time for the thread to block in its read of stdin.
            await asyncio.sleep(0.5)
            started = time.monotonic()
            subprocess.run([sys.executable, "-c", "pass"], check=True, timeout=20)
            seconds = time.monotonic() - started
            line = await reader.readline()
            writer.write(json.dumps({"seconds": seconds, "line": line.decode()}).encode())
            await flush_and_close(writer)

        asyncio.run(main())
    """
    async with _process("synchronous", body) as child:
        assert await asyncio.wait_for(child.reader.readline(), 10) == b"ready\n"
        await asyncio.sleep(5)
        child.writer.write(b"next\n")
        stdout, stderr = await asyncio.wait_for(asyncio.gather(child.reader.read(), child.stderr.read()), 30)
        code = await asyncio.wait_for(child.process.wait(), 10)

    assert code == 0, stderr.decode(errors="replace")
    results = json.loads(stdout)
    assert results["seconds"] < 2
    assert results["line"] == "next\n"


@_WINDOWS_ONLY
async def test_synchronous_pipes_work_on_a_selector_event_loop() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"echo " + await reader.readline())
            await flush_and_close(writer)

        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    """
    stdout, stderr, code = await _run("synchronous", body, b"hello\n")

    assert code == 0, stderr
    assert stdout == b"echo hello\n"


_NATIVE_WRITE = """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
    ]

    async def main():
        reader, writer = await open_stdio_connection()
        text = b"native-marker\\n"
        written = wintypes.DWORD()
        if not kernel32.WriteFile(kernel32.GetStdHandle(-11), text, len(text), ctypes.byref(written), None):
            raise ctypes.WinError(ctypes.get_last_error())
        writer.write(b"done")
        await flush_and_close(writer)

    asyncio.run(main())
"""


@_WINDOWS_ONLY
async def test_a_native_write_to_the_standard_output_handle_appears_on_stderr(pipes: str) -> None:
    stdout, stderr, code = await _run(pipes, _NATIVE_WRITE)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "native-marker" in stderr


@_WINDOWS_ONLY
async def test_a_child_process_that_writes_and_reads_uses_the_moved_streams(pipes: str) -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"ready\\n")
            time.sleep(1)
            started = time.monotonic()
            code = "import sys; print('child-marker', repr(sys.stdin.buffer.read(14)), flush=True)"
            subprocess.run([sys.executable, "-c", code], check=True, timeout=20)
            results = {"seconds": time.monotonic() - started, "reader": (await reader.readline()).decode()}
            writer.write(json.dumps(results).encode())
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _send_once_the_process_is_ready(pipes, body)

    assert code == 0, stderr
    results = json.loads(stdout)
    assert "child-marker b''" in stderr
    assert results["seconds"] < 5
    assert results["reader"] == "protocol-bytes\n"


@_WINDOWS_ONLY
def test_a_console_on_stdin_is_refused(tmp_path: Path) -> None:
    refusal = tmp_path / "refusal.txt"
    body = """
        async def main():
            try:
                await open_stdio_connection()
            except RuntimeError as error:
                with open(sys.argv[1], "w", encoding="utf-8") as file:
                    file.write(str(error))
                raise SystemExit(1)

        asyncio.run(main())
    """

    # Without standard handles of its own, a process with a console of its own reads that console.
    result = subprocess.run(
        [sys.executable, "-c", _script(body), str(refusal)],
        # The flag exists only on Windows, so it is named here, for the type check on other platforms.
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE"),
        timeout=30,
        check=False,
    )

    assert result.returncode == 1
    assert f"{_STDIN_NEEDED}, but stdin is a character device" in refusal.read_text(encoding="utf-8")


@_WINDOWS_ONLY
async def test_overlapped_pipes_on_a_selector_event_loop_are_refused_and_the_streams_stay() -> None:
    body = _REFUSED.replace("asyncio.run(main())", "asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)")

    stdout, stderr, code = await _run("overlapped", body)

    assert code == 1
    assert "RuntimeError: stdio on Windows needs the proactor event loop for overlapped pipes" in stderr
    assert stdout.replace(b"\r\n", b"\n") == b"still on stdout\nstill on file descriptor 1\n"
