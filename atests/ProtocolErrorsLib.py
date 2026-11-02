"""Test-only library, loaded on the server via --pythonpath: a keyword whose return value cannot be transferred."""

from collections.abc import Callable


class ProtocolErrorsLib:
    def return_a_lambda(self) -> Callable[[], None]:
        return lambda: None
