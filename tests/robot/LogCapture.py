"""Client-side listener library that records log messages, used to assert log forwarding."""

from robot import result


class LogCapture:
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self) -> None:
        self.ROBOT_LIBRARY_LISTENER = self
        self._messages: list[str] = []

    def log_message(self, message: "result.Message") -> None:
        self._messages.append(message.message)

    def get_captured_log_messages(self) -> list[str]:
        return list(self._messages)
