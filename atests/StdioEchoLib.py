"""Echo library for the stdio suites."""


class StdioEchoLib:
    ROBOT_LIBRARY_SCOPE = "TEST"
    ROBOT_LIBRARY_VERSION = "1.0"

    def echo(self, message: str = "qwerty") -> str:
        return f"echo: {message}"
