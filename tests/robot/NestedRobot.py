"""Runs a Robot Framework suite in its own process and reads its result.

For checks of what Robot Framework does with a message at a moment that the running suite cannot
observe itself, such as the end of a suite.
"""

import subprocess
import sys
from pathlib import Path

from robot.api import ExecutionResult


class NestedRobot:
    def run_nested_suite(self, suite: str, output_dir: str, *variables: str) -> str:
        """Runs ``suite`` with ``python -m robot`` and returns its output file; fails if one of its tests fails.

        ``variables`` are ``name:value`` items, passed with ``--variable``.
        """
        output = Path(output_dir) / "output.xml"
        command = [sys.executable, "-m", "robot", "--output", str(output), "--log", "NONE", "--report", "NONE"]
        for variable in variables:
            command += ["--variable", variable]
        completed = subprocess.run([*command, suite], capture_output=True, text=True, timeout=120, check=False)
        if completed.returncode != 0:
            raise AssertionError(
                f"Nested suite failed with exit code {completed.returncode}:\n{completed.stdout}{completed.stderr}"
            )
        return str(output)

    def get_execution_errors(self, output: str) -> list[str]:
        """Returns the messages that the output file ``output`` lists as execution errors."""
        return [str(message.message) for message in ExecutionResult(output).errors.messages]
