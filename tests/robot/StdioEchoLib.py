"""Minimal echo library for the stdio transport suite.

Unlike ``JsonRpcRemote.Echo`` this keyword does NOT ``print``: in stdio mode the
server's stdout carries the JSON-RPC frames, so any write to stdout from a keyword
would corrupt the stream. Use stderr (or RF logging) instead.
"""


class StdioEchoLib:
    ROBOT_LIBRARY_SCOPE = "TEST"
    ROBOT_LIBRARY_VERSION = "1.0"

    def echo(self, message: str = "qwerty") -> str:
        """Return the given message prefixed with 'echo: ' (no stdout writes)."""
        return f"echo: {message}"
