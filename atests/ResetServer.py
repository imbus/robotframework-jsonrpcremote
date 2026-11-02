"""Robot library with a TCP server that resets every connection once the client has sent something."""

import contextlib
import socket
import struct
import sys
import threading


class ResetServer:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self) -> None:
        self._thread: "threading.Thread | None" = None
        self._stop = threading.Event()

    def start_reset_server(self, port: int) -> None:
        """Listen on ``port`` until ``stop_reset_server`` is called.

        The server reads from each connection before it resets it, so the client has written its
        request by then.
        """
        listener = socket.create_server(("127.0.0.1", port))
        listener.settimeout(0.1)
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, args=(listener,), daemon=True)
        self._thread.start()

    def stop_reset_server(self) -> None:
        """Stop listening and close the port."""
        if self._thread is None:
            return

        self._stop.set()
        self._thread.join(5)
        self._thread = None

    def _serve(self, listener: socket.socket) -> None:
        with listener:
            while not self._stop.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    connection.settimeout(5)
                    with contextlib.suppress(OSError):
                        connection.recv(1)
                    # With a zero linger time, closing the socket sends a reset instead of a FIN.
                    linger = struct.pack("HH" if sys.platform == "win32" else "ii", 1, 0)
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
