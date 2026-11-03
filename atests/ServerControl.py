"""Robot library to start/stop the real JSON-RPC remote server for integration tests."""

import socket
import subprocess
import sys
import time


class ServerControl:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self) -> None:
        self._process: "subprocess.Popen[bytes] | None" = None
        self._port: int = 0
        self._last_returncode: "int | None" = None
        self._killed: bool = False

    def start_jsonrpc_server(
        self,
        libraries: str,
        port: int = 8271,
        pythonpath: str = "",
        variables: str = "",
        timeout: float = 20.0,
        wait: bool = True,
        send_tracebacks: bool = False,
        variablefile: str = "",
    ) -> None:
        """Start the real server as a subprocess and wait until it accepts connections.

        ``libraries`` and ``variables`` (``name:value``) are whitespace-separated lists.
        With ``wait`` false, it returns at once, so that calls can be made while the server starts.
        """
        if self._process is not None:
            raise RuntimeError("JSON-RPC server is already running")

        command = [sys.executable, "-m", "robot_jsonrpcremote_server", "--port", str(port)]
        if send_tracebacks:
            command += ["--send-tracebacks"]
        if pythonpath:
            command += ["--pythonpath", pythonpath]
        for variable in variables.split():
            command += ["--variable", variable]
        if variablefile:
            command += ["--variablefile", variablefile]
        command += libraries.split()

        self._process = subprocess.Popen(command)
        self._port = int(port)
        if wait:
            self._wait_for_port("127.0.0.1", int(port), float(timeout))

    def stop_jsonrpc_server(self) -> None:
        """Terminate the server subprocess, killing it if it does not stop in time.

        Records the exit code and whether a ``kill()`` fallback was needed, so tests can
        assert the server shut down gracefully (exit code 0, no kill).
        """
        if self._process is None:
            return

        self._killed = False
        self._process.terminate()
        try:
            self._last_returncode = self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._killed = True
            self._process.kill()
            self._last_returncode = self._process.wait(timeout=10)
        finally:
            self._process = None
        self._wait_until_port_is_closed()

    def kill_jsonrpc_server(self) -> None:
        """Kill the server subprocess without letting it shut down, like a crash or a container restart.

        Records the exit code like ``stop_jsonrpc_server``.
        """
        if self._process is None:
            return

        self._killed = True
        self._process.kill()
        try:
            self._last_returncode = self._process.wait(timeout=10)
        finally:
            self._process = None
        self._wait_until_port_is_closed()

    def wait_for_jsonrpc_server_to_exit(self, timeout: float = 10.0) -> int:
        """Wait until the server process exits on its own and return its exit code.

        Records the exit code like ``stop_jsonrpc_server``. A server that does not exit
        within ``timeout`` is killed, which ``server_was_killed`` reports.
        """
        if self._process is None:
            raise RuntimeError("JSON-RPC server is not running")

        self._killed = False
        try:
            self._last_returncode = self._process.wait(timeout=float(timeout))
        except subprocess.TimeoutExpired:
            self._killed = True
            self._process.kill()
            self._last_returncode = self._process.wait(timeout=10)
        finally:
            self._process = None
        self._wait_until_port_is_closed()
        return self._last_returncode

    def get_server_exit_code(self) -> int:
        """Return the exit code recorded by the last ``stop_jsonrpc_server`` call."""
        if self._last_returncode is None:
            raise RuntimeError("Server has not been stopped yet")
        return self._last_returncode

    def server_was_killed(self) -> bool:
        """Return whether the last stop needed a ``kill()`` fallback (i.e. ungraceful)."""
        return self._killed

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

    def _wait_until_port_is_closed(self, timeout: float = 10.0) -> None:
        """Wait until the stopped server no longer accepts connections.

        In a venv on Windows, the process is a launcher with the real interpreter as its child, and that
        child still accepts connections for a moment after the launcher has ended.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                # A listening port on this machine answers at once, so a timeout counts as closed: on
                # Windows, a connection attempt to a closed port takes about 2 seconds.
                with socket.create_connection(("127.0.0.1", self._port), timeout=0.2):
                    time.sleep(0.01)
            except OSError:
                return

        raise RuntimeError(f"Port {self._port} still accepts connections {timeout}s after the server stopped")
