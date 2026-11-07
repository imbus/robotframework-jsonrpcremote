import subprocess
import sys

from robot.api import logger


class MyLibrary:
    """A regular Robot Framework library: nothing in it knows that it runs on a server."""

    def greet(self, name: str) -> str:
        """Returns a greeting for ``name``."""
        logger.info(f"Greeting {name}")
        return f"Hello, {name}!"

    def greet_from_a_child_process(self, name: str) -> str:
        """Returns a greeting for ``name``, after a child process has written one to its stdout."""
        subprocess.run([sys.executable, "-c", f"print('Hello from a child process, {name}!')"], check=True)
        return f"Hello, {name}!"
