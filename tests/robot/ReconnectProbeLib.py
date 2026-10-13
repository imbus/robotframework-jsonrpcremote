"""Test-only server library for the reconnect suites: it can end its own server process.

Never writes to stdout, so it also works with the stdio transport.
"""

import os
import tempfile


class ReconnectProbeLib:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def echo(self, message: str = "ping") -> str:
        """Returns the given message prefixed with 'echo: '."""
        return f"echo: {message}"

    def exit_server(self, record_file: str = "", exit_code: int = 3) -> None:
        """Terminates the server process immediately, while this keyword call is running.

        If ``record_file`` is given, a line is appended to that file in the temp directory
        first, so a test can count how often the keyword actually reached the server. It is
        a file name rather than a path, so no backslashes of a Windows path are sent as a
        keyword argument.
        """
        if record_file:
            with open(os.path.join(tempfile.gettempdir(), record_file), "a", encoding="utf-8") as file:
                file.write("called\n")
        os._exit(exit_code)
