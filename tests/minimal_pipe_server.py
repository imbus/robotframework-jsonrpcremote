"""A small standalone server over a pipe, with only the standard library, as a server in another language would be.

It connects to the address of its ``--pipe=`` argument with plain blocking I/O: a pipe opened with
``open()`` on Windows, a Unix domain socket elsewhere. It prints a line to its stdout, and a child
process prints another, so that tests see where the output of a server goes. Then it serves as
``minimal_stdio_server`` does: it answers the handshake, offers the keyword ``Echo`` and exits at the
end of its input.
"""

import io
import socket
import subprocess
import sys
from typing import IO

from minimal_stdio_server import serve


def _connect(address: str) -> tuple[IO[bytes], IO[bytes]]:
    streams: tuple[IO[bytes], IO[bytes]]
    if sys.platform == "win32":
        # Synchronous I/O handles one operation at a time, which suits a server that reads a request
        # and then writes its response.
        pipe = open(address, "r+b", buffering=0)
        streams = io.BufferedReader(pipe), io.BufferedWriter(pipe)
    else:
        connection = socket.socket(socket.AF_UNIX)
        connection.connect(address)
        streams = connection.makefile("rb"), connection.makefile("wb")
    return streams


def main() -> None:
    address = next(arg.removeprefix("--pipe=") for arg in reversed(sys.argv) if arg.startswith("--pipe="))
    reader, writer = _connect(address)
    print("minimal pipe server: a line from the server", flush=True)
    subprocess.run([sys.executable, "-c", "print('minimal pipe server: a line from its child')"], check=True)
    serve(reader, writer)


if __name__ == "__main__":
    main()
