"""Test-only library, loaded on the server, with the scope GLOBAL: counts its calls and has a listener of its own.

The listener appends its events to a file with a fixed name in the temp directory, as ``ConnectionLossLib`` writes
its record there. A path among the import arguments would be part of the key under which Robot Framework caches the
library, so suites remove the file before they start the server instead.
"""

import os
import tempfile

from robot import result, running

EVENTS_FILE = os.path.join(tempfile.gettempdir(), "jsonrpcremote-global-counter-events.txt")


def _record(line: str) -> None:
    with open(EVENTS_FILE, "a", encoding="utf-8") as file:
        file.write(f"{line}\n")


class _Listener:
    ROBOT_LISTENER_API_VERSION = 3

    def start_keyword(self, data: running.Keyword, result: result.Keyword) -> None:
        _record(f"start_keyword {data.name} {' '.join(str(arg) for arg in data.args)}")

    def close(self) -> None:
        _record("close")


class GlobalCounterLib:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self) -> None:
        self._calls = 0
        self.ROBOT_LIBRARY_LISTENER = _Listener()

    def count(self, caller: str = "") -> int:
        """Returns how often this instance was called, this call included; ``caller`` names the call in the events."""
        self._calls += 1
        return self._calls

    def end_server_process(self) -> None:
        """Ends the server process with exit code 3, as a crash would."""
        os._exit(3)
