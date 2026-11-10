"""Test-only library, loaded on the server, with the scope TEST: counts the calls of its instance."""


class TestCounterLib:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def __init__(self) -> None:
        self._calls = 0

    def count(self, caller: str = "") -> int:
        """Returns how often this instance was called, this call included."""
        self._calls += 1
        return self._calls
