"""Test-only library, loaded on the server via --pythonpath: logs a warning when the server finalizes it.

It is its own library listener with scope SUITE, so finalizing the library at the end of a session
calls ``_close``, outside any keyword call of the client.
"""

from robot.api import logger


class CloseLogLib:
    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self) -> None:
        self.ROBOT_LIBRARY_LISTENER = self

    def ping(self) -> str:
        """Returns ``pong``."""
        return "pong"

    def _close(self) -> None:
        logger.warn("CloseLogLib was finalized")
