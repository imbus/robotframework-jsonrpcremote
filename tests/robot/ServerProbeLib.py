"""Test-only library, loaded on the server via --pythonpath, to probe server behavior.

Used by the integration suite to verify that (a) a library outside the installed
packages can be imported through --pythonpath, (b) init-argument types survive the
JSON-RPC round trip, and (c) server --variable settings reach keyword execution.
"""

from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn


class ServerProbeLib:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._init_args = list(args)
        self._init_kwargs = dict(kwargs)

    def get_init_args(self) -> list[object]:
        """Returns the positional arguments this library was initialized with."""
        return list(self._init_args)

    def get_init_arg_types(self) -> list[str]:
        """Returns the type names of the positional init arguments."""
        return [type(arg).__name__ for arg in self._init_args]

    def get_init_kwargs(self) -> dict[str, object]:
        """Returns the keyword arguments this library was initialized with."""
        return dict(self._init_kwargs)

    def get_robot_variable(self, name: str) -> object:
        """Returns the value of the Robot variable ``${name}`` from the server context."""
        return BuiltIn().get_variable_value("${" + name + "}")

    def echo_value(self, value: object) -> object:
        """Returns the given value unchanged (for argument/return round-trip tests)."""
        return value

    def type_name_of(self, value: object) -> str:
        """Returns the type name of the value as it arrived on the server."""
        return type(value).__name__

    def format_pair(self, first: object, second: object) -> str:
        """Joins two (possibly named) arguments, for keyword-call kwargs tests."""
        return f"{first}/{second}"

    def fail_with(self, message: str) -> None:
        """Raises an error, to check that failures propagate back to the client."""
        raise RuntimeError(message)

    def emit_log(self, message: str) -> str:
        """Logs a message on the server; it should be forwarded to the client."""
        logger.info(message)
        return message
