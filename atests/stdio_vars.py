"""Variables for the stdio transport suites: the ``stdio:<command>`` server commands."""

import os
import shlex
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))


def _server_command(library: str) -> str:
    """The command of our server for ``library``, quoted, so that a path with a space survives the client's split."""
    return shlex.join([sys.executable, "-m", "robot_jsonrpcremote_server", "--stdio", "--pythonpath", _HERE, library])


SERVER_COMMAND = _server_command("StdioEchoLib")
PROBE_SERVER_COMMAND = _server_command("ServerProbeLib")
LOSS_SERVER_COMMAND = _server_command("ConnectionLossLib")
OUTPUT_SERVER_COMMAND = _server_command("StdioOutputLib")
# Where StdioOutputLib on the server writes the PID of the child process that keeps running.
CHILD_PID_FILE = os.path.join(tempfile.gettempdir(), "jsonrpcremote-stdio-output-child.pid")
# The hand-written example server, which prints on every message.
OWN_SERVER_COMMAND = shlex.join([sys.executable, "-m", "simple_robot_jsonrpcserver", "--stdio"])
