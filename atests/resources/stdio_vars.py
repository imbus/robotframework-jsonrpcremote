"""Variables for the stdio transport suites: the ``stdio:<command>`` server commands."""

import os
import shlex
import sys
import tempfile

# The libraries of the servers, with the Node server and its wrapper script.
_LIBRARIES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libraries")


def _server_args(library: str) -> list[str]:
    """The arguments of our server for ``library``, for the suites that give the command as a list."""
    return [sys.executable, "-m", "robot_jsonrpcremote_server", "--stdio", "--pythonpath", _LIBRARIES, library]


def _server_command(library: str) -> str:
    """The command of our server for ``library``, quoted, so that a path with a space survives the client's split."""
    return shlex.join(_server_args(library))


SERVER_COMMAND = _server_command("StdioEchoLib")
SERVER_ARGS = _server_args("StdioEchoLib")
PROBE_SERVER_COMMAND = _server_command("ServerProbeLib")
LOSS_SERVER_COMMAND = _server_command("ConnectionLossLib")
GLOBAL_COUNTER_COMMAND = _server_command("GlobalCounterLib")
OUTPUT_SERVER_COMMAND = _server_command("StdioOutputLib")
# Where StdioOutputLib on the server writes the PID of the child process that keeps running.
CHILD_PID_FILE = os.path.join(tempfile.gettempdir(), "jsonrpcremote-stdio-output-child.pid")
# The hand-written example server, which prints on every message.
OWN_SERVER_COMMAND = shlex.join([sys.executable, "-m", "simple_robot_jsonrpcserver", "--stdio"])
# A server written in Node, and the same server started by a wrapper script, which is a .cmd file on Windows.
NODE_SERVER_COMMAND = shlex.join(["node", os.path.join(_LIBRARIES, "node_keywords.js")])
NODE_WRAPPER_COMMAND = shlex.join([os.path.join(_LIBRARIES, "node_keywords.cmd")])
