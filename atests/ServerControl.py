"""Robot library to start/stop the real JSON-RPC remote server for integration tests."""

import socket
import subprocess
import sys
import time

from jsonrpcpeer import pipe_address


def _connect_to_pipe(name: str) -> None:
    """Connect to the pipe ``name`` and close the connection at once; raise ``OSError`` if that fails."""
    address = pipe_address(name)
    if sys.platform == "win32":
        open(address, "r+b", buffering=0).close()
    else:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(1.0)
            connection.connect(address)


class ServerControl:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self) -> None:
        self._process: "subprocess.Popen[bytes] | None" = None
        self._port: int = 0
        # The pipe that the server listens on instead of a port.
        self._pipe: "str | None" = None
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
        pipe: str = "",
    ) -> None:
        """Start the real server as a subprocess and wait until it accepts connections.

        ``libraries`` and ``variables`` (``name:value``) are whitespace-separated lists.
        With ``wait`` false, it returns at once, so that calls can be made while the server starts.
        With ``pipe``, the server listens on the pipe of that name, with ``--pipe-server``, instead of a port.
        """
        if self._process is not None:
            raise RuntimeError("JSON-RPC server is already running")

        command = [sys.executable, "-m", "robot_jsonrpcremote_server"]
        command += ["--pipe-server", pipe] if pipe else ["--port", str(port)]
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
        self._pipe = pipe or None
        if wait and self._pipe is not None:
            self._wait_for_pipe(self._pipe, float(timeout))
        elif wait:
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
        self._wait_until_closed()

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
        self._wait_until_closed()

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
        self._wait_until_closed()
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

    def _wait_for_pipe(self, name: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_error: OSError | None = None
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(f"Server process exited early with code {self._process.returncode}")
            try:
                _connect_to_pipe(name)
                return
            except OSError as error:
                last_error = error
                time.sleep(0.2)

        raise RuntimeError(f"Server not reachable on the pipe {name} within {timeout}s: {last_error}")

    def _wait_until_closed(self) -> None:
        if self._pipe is not None:
            self._wait_until_pipe_is_gone(self._pipe)
        else:
            self._wait_until_port_is_closed()

    def _wait_until_pipe_is_gone(self, name: str, timeout: float = 10.0) -> None:
        """Wait until nobody listens on the pipe of the stopped server, as for its port."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                _connect_to_pipe(name)
            except (FileNotFoundError, ConnectionRefusedError):
                # Gone, or a socket file that a killed server left behind.
                return
            except OSError:
                # On Windows, a busy pipe: its name is still there.
                pass
            time.sleep(0.01)

        raise RuntimeError(f"Pipe {name} still accepts connections {timeout}s after the server stopped")

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
