"""Runs a Robot Framework suite in its own process and reads its result.

For checks of what Robot Framework does with a message at a moment that the running suite cannot
observe itself, such as the end of a suite, and of how a run ends, such as after a fatal failure.
"""

import subprocess
import sys
from pathlib import Path

from robot import result
from robot.api import ExecutionResult, ResultVisitor


class _MessageCollector(ResultVisitor):
    def __init__(self, level: str) -> None:
        self.level = level
        self.messages: list[str] = []

    def visit_message(self, message: "result.Message") -> None:
        if message.level == self.level:
            self.messages.append(str(message.message))


class NestedRobot:
    def __init__(self) -> None:
        self._console_output = ""

    def run_nested_suite(
        self,
        suite: str,
        output_dir: str,
        *variables: str,
        log_level: str = "INFO",
        allow_failures: bool = False,
        max_error_lines: str = "",
    ) -> str:
        """Runs ``suite`` with ``python -m robot`` and returns its output file.

        Fails if one of its tests fails, unless ``allow_failures`` is true. ``variables`` are ``name:value``
        items, passed with ``--variable``. ``max_error_lines`` is passed with ``--maxerrorlines``, if given.
        """
        output = Path(output_dir) / "output.xml"
        command = [sys.executable, "-m", "robot", "--output", str(output), "--log", "NONE", "--report", "NONE"]
        command += ["--loglevel", log_level]
        if allow_failures:
            command += ["--nostatusrc"]
        if max_error_lines:
            command += ["--maxerrorlines", max_error_lines]
        for variable in variables:
            command += ["--variable", variable]
        completed = subprocess.run([*command, suite], capture_output=True, text=True, timeout=120, check=False)
        self._console_output = completed.stdout + completed.stderr
        if completed.returncode != 0:
            raise AssertionError(
                f"Nested suite failed with exit code {completed.returncode}:\n{completed.stdout}{completed.stderr}"
            )
        return str(output)

    def get_console_output(self) -> str:
        """Returns what the last nested run wrote to the console."""
        return self._console_output

    def get_execution_errors(self, output: str) -> list[str]:
        """Returns the messages that the output file ``output`` lists as execution errors."""
        return [str(message.message) for message in ExecutionResult(output).errors.messages]

    def get_test_results(self, output: str) -> dict[str, str]:
        """Returns ``status: message`` of each test in the output file ``output``, by the name of the test."""
        return {test.name: f"{test.status}: {test.message}" for test in ExecutionResult(output).suite.all_tests}

    def get_messages(self, output: str, test: str, level: str) -> list[str]:
        """Returns the messages at exactly ``level`` under the keywords of ``test`` in the output file ``output``."""
        collector = _MessageCollector(level)
        for candidate in ExecutionResult(output).suite.all_tests:
            if candidate.name == test:
                candidate.visit(collector)
        return collector.messages

    def get_messages_by_keyword(self, output: str, test: str) -> list[str]:
        """Returns ``keyword: message`` for the messages under the keywords of ``test`` in the file ``output``."""
        return [
            f"{keyword.full_name}: {message.message}"
            for candidate in ExecutionResult(output).suite.all_tests
            if candidate.name == test
            for keyword in candidate.body
            for message in keyword.messages
        ]
