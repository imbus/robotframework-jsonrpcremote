"""Test-only library that only the server can import, as in a container.

`atests/library/server_only_library.robot` starts its server with this folder on the module search path. The Robot
run has no path to it, so the client cannot import the classes of the defaults.
"""

from enum import Enum
from typing import Any


class Button(Enum):
    LEFT = 1
    RIGHT = 2


class ServerOnlyLib:
    def click(self, button: Button = Button.LEFT) -> str:
        """Returns the name of the button."""
        return button.name

    def call(self, f: Any = lambda: 1) -> Any:
        """Returns what ``f`` returns; its default cannot be pickled."""
        return f()
