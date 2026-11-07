"""The connection over the stdin and stdout of a process, each scenario in a process of its own.

``open_stdio_connection()`` changes the file descriptors of its process, so it cannot run in the
process of the tests: pytest's capture and every later test would break.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import IO

import pytest

from jsonrpcpeer import JsonRpcPeer

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stdio transport is POSIX-only")

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


@asynccontextmanager
async def _process(body: str, stderr: int = asyncio.subprocess.PIPE) -> AsyncIterator[asyncio.subprocess.Process]:
    """A process that runs ``body`` with pipes on its stdin and stdout; it is killed if it is still running."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _script(body),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=stderr,
    )
    try:
        yield process
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        await process.wait()


async def _run(body: str, data: bytes = b"") -> tuple[bytes, str, int]:
    """Run ``body``, send it ``data`` and close its stdin; return its stdout, stderr and exit code."""
    async with _process(body) as process:
        stdout, stderr = await asyncio.wait_for(process.communicate(data), 30)
    assert process.returncode is not None
    return stdout, stderr.decode(errors="replace"), process.returncode


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


async def test_a_peer_on_the_pair_answers_a_request() -> None:
    body = """
        from jsonrpcpeer import JsonRpcPeer

        async def echo(params: dict[str, str]) -> dict[str, str]:
            return params

        async def main():
            peer = JsonRpcPeer(*await open_stdio_connection())
            peer.register_request_handler("echo", echo)
            await peer.run()

        asyncio.run(main())
    """
    async with _process(body) as process:
        assert process.stdout is not None
        assert process.stdin is not None
        peer = JsonRpcPeer(process.stdout, process.stdin)
        peer.start()
        result = await asyncio.wait_for(peer.send_request("echo", {"text": "Grüße"}), 10)
        # Closing our end ends the input of the process, and its peer ends.
        await peer.stop()
        await asyncio.wait_for(process.wait(), 10)

    assert result == {"text": "Grüße"}
    assert process.returncode == 0


async def test_large_messages_pass_unchanged() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            size = int(await reader.readline())
            writer.write(await reader.readexactly(size))
            await flush_and_close(writer)

        asyncio.run(main())
    """
    payload = os.urandom(4 * 1024 * 1024)

    stdout, stderr, code = await _run(body, b"%d\n" % len(payload) + payload)

    assert code == 0, stderr
    assert stdout == payload


async def test_print_appears_on_stderr_at_the_end_of_its_line() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            print("print-marker")
            await reader.readline()
            writer.write(b"done")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    async with _process(body) as process:
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        # The process waits for our line, so it still runs when its line arrives.
        line = await asyncio.wait_for(process.stderr.readline(), 10)
        process.stdin.write(b"go\n")
        stdout = await asyncio.wait_for(process.stdout.read(), 10)

    assert line == b"print-marker\n"
    assert stdout == b"done"


async def test_direct_writes_to_file_descriptor_1_appear_on_stderr() -> None:
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
    stdout, stderr, code = await _run(body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "file-descriptor-marker" in stderr
    assert "dunder-stdout-marker" in stderr


async def test_output_of_child_processes_appears_on_stderr() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            subprocess.run([sys.executable, "-c", "print('subprocess-marker')"], check=True, timeout=20)
            os.system(shlex.join([sys.executable, "-c", "print('os-system-marker')"]))
            writer.write(b"done")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "subprocess-marker" in stderr
    assert "os-system-marker" in stderr


async def test_text_buffered_before_the_call_appears_on_stderr() -> None:
    body = """
        # stdout is a pipe, so this stays in the buffer of sys.stdout.
        sys.stdout.write("buffered-marker\\n")

        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"done")
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "buffered-marker" in stderr


async def test_print_after_the_connection_has_closed_appears_on_stderr() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"done")
            await flush_and_close(writer)
            await asyncio.sleep(0.1)
            print("after-close-marker", flush=True)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(body)

    assert code == 0, stderr
    assert stdout == b"done"
    assert "after-close-marker" in stderr
    assert "Traceback" not in stderr


async def _send_once_the_process_is_ready(body: str) -> tuple[bytes, str, int]:
    """Run ``body``, which writes a line when it is ready and then waits; send it the data of the connection."""
    async with _process(body) as process:
        assert process.stdin is not None
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 10) == b"ready\n"
        # The process does not run its event loop now, so the data waits on its stdin.
        process.stdin.write(b"protocol-bytes\n")
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode is not None
    return stdout, stderr.decode(errors="replace"), process.returncode


async def test_reading_stdin_in_the_process_gets_nothing_of_the_connection() -> None:
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
    stdout, stderr, code = await _send_once_the_process_is_ready(body)

    assert code == 0, stderr
    assert json.loads(stdout) == {
        "input": "EOFError",
        "sys.stdin": "",
        "os.read": "",
        "reader": "protocol-bytes\n",
    }


async def test_a_child_process_that_reads_stdin_sees_its_end_at_once() -> None:
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
    stdout, stderr, code = await _send_once_the_process_is_ready(body)

    assert code == 0, stderr
    results = json.loads(stdout)
    assert results["child"] == "b''"
    assert results["seconds"] < 5
    assert results["reader"] == "protocol-bytes\n"


async def test_a_child_process_does_not_keep_the_connection_open() -> None:
    body = """
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
    # The child process would inherit a pipe on stderr, which would keep it open too.
    async with _process(body, stderr=asyncio.subprocess.DEVNULL) as process:
        assert process.stdout is not None
        child_pid = int(await asyncio.wait_for(process.stdout.readline(), 10))
        started = time.monotonic()
        try:
            rest = await asyncio.wait_for(process.stdout.read(), 12)
            seconds = time.monotonic() - started
        finally:
            with suppress(ProcessLookupError):
                os.kill(child_pid, signal.SIGTERM)
        await asyncio.wait_for(process.wait(), 10)

    assert rest == b""
    assert seconds < 10
    assert process.returncode == 3


def test_stdin_that_is_the_null_device_is_refused_and_the_streams_stay() -> None:
    with open(os.devnull) as null:
        result = _run_refused(null)

    assert result.returncode == 1
    assert f"{_STDIN_NEEDED}, but stdin is a character device" in result.stderr
    assert result.stdout == "still on stdout\nstill on file descriptor 1\n"


def test_stdin_that_is_a_regular_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "stdin.txt"
    path.write_text("")
    with path.open() as file:
        result = _run_refused(file)

    assert result.returncode == 1
    assert f"{_STDIN_NEEDED}, but stdin is a regular file" in result.stderr


def test_a_closed_stdin_is_refused() -> None:
    result = _run_refused(subprocess.PIPE, closing="0<&-")

    assert result.returncode == 1
    assert f"{_STDIN_NEEDED}, but stdin is closed" in result.stderr


def test_a_closed_stdout_is_refused() -> None:
    result = _run_refused(subprocess.PIPE, closing="1>&-")

    assert result.returncode == 1
    assert "stdio mode needs an open stdout, but stdout is closed" in result.stderr


async def test_a_pipe_whose_writing_end_is_closed_is_a_valid_stdin() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            writer.write(b"read %r" % await reader.read())
            await flush_and_close(writer)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(body)

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


def test_a_process_that_starts_without_a_stderr_keeps_the_connection_clean() -> None:
    # The selector of the event loop then gets file descriptor 2.
    stdout, code = _run_without_stderr(_WITHOUT_STDERR.format(close="pass"), b"line\n")

    assert code == 0
    assert stdout == b"echo line\n"


async def test_a_stderr_closed_before_the_call_keeps_the_connection_clean() -> None:
    # The process started with a stderr, so file descriptor 2 is free when the function runs.
    stdout, _, code = await _run(_WITHOUT_STDERR.format(close="os.close(2)"), b"line\n")

    assert code == 0
    assert stdout == b"echo line\n"


async def test_closing_the_writer_ends_the_connection_in_both_directions() -> None:
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
    async with _process(body) as process:
        assert process.stdout is not None
        assert process.stderr is not None
        # Our end of its stdin stays open: the reader ends because the writer was closed.
        stdout = await asyncio.wait_for(process.stdout.read(), 10)
        stderr = (await asyncio.wait_for(process.stderr.read(), 10)).decode(errors="replace")
        await asyncio.wait_for(process.wait(), 10)

    assert process.returncode == 0, stderr
    assert stdout == b"hello"
    assert "reader got b''" in stderr


async def test_the_writer_stays_usable_when_the_input_ends() -> None:
    body = """
        async def main():
            reader, writer = await open_stdio_connection()
            data = await asyncio.wait_for(reader.read(), 5)
            writer.write(b"bye " + data)
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 5)

        asyncio.run(main())
    """
    stdout, stderr, code = await _run(body, b"data")

    assert code == 0, stderr
    assert stdout == b"bye data"


def test_the_other_end_going_away_ends_the_connection_without_unretrieved_errors() -> None:
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
    # A pipe of our own on its stdin, open until the end: the reader must end because stdout went away.
    stdin_read, stdin_write = os.pipe()
    try:
        process = subprocess.Popen(
            [sys.executable, "-X", "dev", "-c", _script(body)],
            stdin=stdin_read,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        os.close(stdin_read)
        assert process.stdout is not None
        try:
            process.stdout.read(1024)
            process.stdout.close()
            _, stderr_bytes = process.communicate(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    finally:
        os.close(stdin_write)
    stderr = stderr_bytes.decode(errors="replace")

    assert process.returncode == 0, stderr
    assert "connection error True, reader got b''" in stderr
    for report in ("never retrieved", "ResourceWarning", "unclosed"):
        assert report not in stderr
