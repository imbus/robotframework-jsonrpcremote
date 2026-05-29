"""Test-only library, loaded on the server via --pythonpath, to probe server behavior.

Used by the integration suite to verify that (a) a library outside the installed
packages can be imported through --pythonpath, (b) init-argument types survive the
JSON-RPC round trip, and (c) server --variable settings reach keyword execution.
"""

from robot.libraries.BuiltIn import BuiltIn


class ServerProbeLib:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def __init__(self, *args: object) -> None:
        self._init_args = list(args)

    def get_init_args(self) -> list[object]:
        """Returns the positional arguments this library was initialized with."""
        return list(self._init_args)

    def get_init_arg_types(self) -> list[str]:
        """Returns the type names of the positional init arguments."""
        return [type(arg).__name__ for arg in self._init_args]

    def get_robot_variable(self, name: str) -> object:
        """Returns the value of the Robot variable ``${name}`` from the server context."""
        return BuiltIn().get_variable_value("${" + name + "}")
