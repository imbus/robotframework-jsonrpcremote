"""Test-only library, loaded on the server, that ends or stops the server process during a keyword call.

It never writes to stdout, so it also works over stdio, where stdout carries the JSON-RPC frames.
"""

import os
import signal
import tempfile
import time


class ConnectionLossLib:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def echo(self, message: str) -> str:
        return f"echo: {message}"

    def exit_server(self, record: str, exit_code: int = 0) -> None:
        """Appends a line to the file ``record`` in the temp directory, then ends the server process.

        ``record`` is a file name rather than a path, so suites need not escape paths. The
        record shows how often the server ran this keyword.
        """
        with open(os.path.join(tempfile.gettempdir(), record), "a", encoding="utf-8") as file:
            file.write("exit server\n")
        os._exit(exit_code)

    def terminate_server(self, value: str) -> str:
        """Sends SIGTERM to the server process and returns ``value`` while the server stops (POSIX only)."""
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.5)
        return value
