"""Test-only library, loaded on the server via --pythonpath: a keyword for each way a keyword can fail."""

from robot.api import ContinuableFailure, FatalError, SkipExecution


class FailureModesLib:
    def fail_with_value_error(self) -> None:
        raise ValueError("bad value")

    def fail_with_a_long_message(self) -> None:
        raise AssertionError("\n".join(f"line {number}" for number in range(1, 101)))

    def skip_the_test(self) -> None:
        raise SkipExecution("not today")

    def fail_continuably(self) -> None:
        raise ContinuableFailure("go on")

    def fail_fatally(self) -> None:
        raise FatalError("stop all")

    def ping(self) -> str:
        return "pong"
