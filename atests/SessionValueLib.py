"""Test-only library, loaded on the server via --pythonpath: keeps a value per library instance.

Each session imports the library anew, so a value remembered in one session is gone in the next one.
"""


class SessionValueLib:
    def __init__(self) -> None:
        self._value: str | None = None

    def remember_value(self, value: str) -> None:
        """Keeps ``value`` as long as this library instance lives."""
        self._value = value

    def recalled_value(self) -> str | None:
        """Returns the value kept by ``Remember Value``, or ``None`` if there is none."""
        return self._value
