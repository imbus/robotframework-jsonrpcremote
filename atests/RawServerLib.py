"""Test-only library: a server that breaks the protocol on purpose, because only a raw server can send broken frames."""

import inspect
import json
import socketserver
import threading
import time
from collections.abc import Callable
from typing import Any

from robot.api import logger

_RESULTS: dict[str, Any] = {
    "robot/initialize": {"capabilities": {"support_exit": False}, "server_info": {"name": "raw", "version": "1"}},
    "robot/import_library": {
        "token": "t",
        "definition": {"name": "Raw", "keywords": [{"name": "Say Hello", "args": []}]},
    },
    "robot/run_keyword": {"result": "hello"},
}
_RUN_KEYWORD = "robot/run_keyword"
_INITIALIZE = "robot/initialize"
_INVALID_LENGTH = b'Content-Length: abc\r\n\r\n{"jsonrpc":"2.0","method":"robot/log","params":{"message":"lost"}}\r\n'


def _frame(message: dict[str, Any], header: str = "Content-Length: {n}") -> bytes:
    body = json.dumps(message).encode()
    return header.replace("{n}", str(len(body))).encode() + b"\r\n\r\n" + body


def _invalid_length_during_a_keyword(method: str, answer: dict[str, Any]) -> list[bytes]:
    return [_INVALID_LENGTH, _frame(answer)] if method == _RUN_KEYWORD else [_frame(answer)]


def _invalid_length_at_the_import(method: str, answer: dict[str, Any]) -> list[bytes]:
    return [_frame(answer, "Content-Length: abc") + b"\r\n"] if method == _INITIALIZE else [_frame(answer)]


def _log_params_that_cannot_be_converted(method: str, answer: dict[str, Any]) -> list[bytes]:
    log = {"jsonrpc": "2.0", "method": "robot/log", "params": {"message": 5, "level": "NOPE"}}
    return [_frame(log), _frame(answer)] if method == _RUN_KEYWORD else [_frame(answer)]


def _error_without_an_id(method: str, answer: dict[str, Any]) -> list[bytes]:
    error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "bad"}}
    return [_frame(error), _frame(answer)] if method == _RUN_KEYWORD else [_frame(answer)]


def _null_error(method: str, answer: dict[str, Any]) -> list[bytes]:
    return [_frame({**answer, "error": None})]


def _lower_case_header(method: str, answer: dict[str, Any]) -> list[bytes]:
    return [_frame(answer, "content-length: {n}")]


def _no_version(method: str, answer: dict[str, Any]) -> list[bytes]:
    if method == _INITIALIZE:
        return [_frame({key: value for key, value in answer.items() if key != "jsonrpc"})]
    return [_frame(answer)]


def _warning_off_the_console(method: str, answer: dict[str, Any]) -> list[bytes]:
    params = {"message": "not for the console", "level": "WARN", "console": False}
    log = {"jsonrpc": "2.0", "method": "robot/log", "params": params}
    return [_frame(log), _frame(answer)] if method == _RUN_KEYWORD else [_frame(answer)]


_MISTAKES: dict[str, Callable[[str, dict[str, Any]], list[bytes]]] = {
    "invalid_length_during_a_keyword": _invalid_length_during_a_keyword,
    "invalid_length_at_the_import": _invalid_length_at_the_import,
    "log_params_that_cannot_be_converted": _log_params_that_cannot_be_converted,
    "error_without_an_id": _error_without_an_id,
    "null_error": _null_error,
    "lower_case_header": _lower_case_header,
    "no_version": _no_version,
    "warning_off_the_console": _warning_off_the_console,
}


class _RawServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, port: int, mistake: Callable[[str, dict[str, Any]], list[bytes]]) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.mistake = mistake


class _Handler(socketserver.StreamRequestHandler):
    server: _RawServer

    def _read_message(self) -> dict[str, Any] | None:
        length = 0
        while True:
            line = self.rfile.readline()
            if not line:
                return None
            if line == b"\r\n":
                break
            name, _, value = line.partition(b":")
            if name.lower() == b"content-length":
                length = int(value)
        message: dict[str, Any] = json.loads(self.rfile.read(length))
        return message

    def handle(self) -> None:
        try:
            while (message := self._read_message()) is not None:
                # Only a request gets an answer.
                if "id" not in message or "method" not in message:
                    continue
                method = message["method"]
                answer = {"jsonrpc": "2.0", "id": message["id"], "result": _RESULTS.get(method, {})}
                for number, chunk in enumerate(self.server.mistake(method, answer)):
                    if number:
                        # So that the client has dealt with the first part while it waits for the answer.
                        time.sleep(0.3)
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except ConnectionError:
            pass


class RawServerLib:
    ROBOT_LIBRARY_SCOPE = "SUITE"

    def __init__(self) -> None:
        self._server: _RawServer | None = None

    def start_raw_server(self, mistake: str, port: int) -> None:
        """Starts a server that answers every request, with the mistake ``mistake``."""
        self._server = _RawServer(port, _MISTAKES[mistake])
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop_raw_server(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def robot_framework_has_the_console_option(self) -> bool:
        """Whether ``logger.write`` can keep a warning off the console, which it can since Robot Framework 7.4."""
        return "console" in inspect.signature(logger.write).parameters
