"""Test-only library, loaded on the server, that writes to stdout and reads stdin past Robot Framework's capture."""

import os
import subprocess
import sys
import tempfile
import threading

from robot.api import logger

CHILD_PID_FILE = os.path.join(tempfile.gettempdir(), "jsonrpcremote-stdio-output-child.pid")


class StdioOutputLib:
    def echo(self, message: str) -> str:
        return f"echo: {message}"

    def run_child_that_prints(self, text: str) -> None:
        subprocess.run([sys.executable, "-c", f"print({text!r})"], check=True, timeout=30)

    def run_shell_command_that_prints(self, text: str) -> None:
        os.system(f"echo {text}")

    def write_to_file_descriptor_one(self, text: str) -> None:
        os.write(1, text.encode() + b"\n")

    def write_to_the_console(self, text: str) -> None:
        logger.console(text)

    def print_from_a_thread_later(self, text: str) -> None:
        """Prints ``text`` from a thread 0.1 seconds after the keyword returned."""
        threading.Timer(0.1, lambda: print(text, flush=True)).start()

    def print_in_the_keyword(self, text: str) -> None:
        print(text)

    def read_stdin_in_a_child(self) -> str:
        code = "import sys; print(repr(sys.stdin.read()))"
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30).stdout.strip()

    def start_child_that_keeps_running(self, seconds: int) -> None:
        """Starts a child process that inherits stdin and stdout, and writes its PID to ``CHILD_PID_FILE``."""
        child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"])
        with open(CHILD_PID_FILE, "w", encoding="utf-8") as file:
            file.write(str(child.pid))

    def exit_server(self, exit_code: int) -> None:
        os._exit(exit_code)
