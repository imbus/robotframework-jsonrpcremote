"""Test-only server library for the reconnect suites: it can end its own server process.

Never writes to stdout, so it also works with the stdio transport.
"""

import os


class ReconnectProbeLib:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def echo(self, message: str = "ping") -> str:
        """Returns the given message prefixed with 'echo: '."""
        return f"echo: {message}"

    def exit_server_after_recording(self, path: str, exit_code: int = 3) -> None:
        """Appends a line to ``path`` and terminates the server process immediately.

        The line lets a test count how often the keyword actually reached the server.
        """
        with open(path, "a", encoding="utf-8") as file:
            file.write("called\n")
        os._exit(exit_code)
