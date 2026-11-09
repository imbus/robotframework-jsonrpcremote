"""Test-only library, loaded on the server, with the scope SUITE: counts the calls of its instance."""


class SuiteCounterLib:
    ROBOT_LIBRARY_SCOPE = "SUITE"

    def __init__(self) -> None:
        self._calls = 0

    def count(self, caller: str = "") -> int:
        """Returns how often this instance was called, this call included."""
        self._calls += 1
        return self._calls
