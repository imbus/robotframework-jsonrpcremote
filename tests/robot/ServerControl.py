"""Robot library to start/stop the real JSON-RPC remote server for integration tests."""

import socket
import subprocess
import sys
import time


class ServerControl:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self) -> None:
        self._process: "subprocess.Popen[bytes] | None" = None

    def start_jsonrpc_server(self, library: str, port: int = 8271, timeout: float = 20.0) -> None:
        """Start `python -m robot_jsonrpcremote_server <library> --port <port>` and wait for the port."""
        if self._process is not None:
            raise RuntimeError("JSON-RPC server is already running")

        self._process = subprocess.Popen(
            [sys.executable, "-m", "robot_jsonrpcremote_server", library, "--port", str(port)]
        )
        self._wait_for_port("127.0.0.1", int(port), float(timeout))

    def stop_jsonrpc_server(self) -> None:
        """Terminate the server subprocess, killing it if it does not stop in time."""
        if self._process is None:
            return

        self._process.terminate()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=10)
        finally:
            self._process = None

    def _wait_for_port(self, host: str, port: int, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_error: OSError | None = None
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(f"Server process exited early with code {self._process.returncode}")
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    return
            except OSError as error:
                last_error = error
                time.sleep(0.2)

        raise RuntimeError(f"Server not reachable on {host}:{port} within {timeout}s: {last_error}")
