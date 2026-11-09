"""Variables for the pipe suites: the ``pipe:<command>`` server commands.

They are those of ``stdio_vars.py`` without a mode option: the client appends ``--pipe=<address>``.
"""

import os
import shlex
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))


def _server_args(library: str) -> list[str]:
    """The arguments of our server for ``library``, for the suites that give the command as a list."""
    return [sys.executable, "-m", "robot_jsonrpcremote_server", "--pythonpath", _HERE, library]


def _server_command(library: str) -> str:
    """The command of our server for ``library``, quoted, so that a path with a space survives the client's split."""
    return shlex.join(_server_args(library))


SERVER_COMMAND = _server_command("StdioEchoLib")
SERVER_ARGS = _server_args("StdioEchoLib")
LOSS_SERVER_ARGS = _server_args("ConnectionLossLib")
PROBE_SERVER_COMMAND = _server_command("ServerProbeLib")
LOSS_SERVER_COMMAND = _server_command("ConnectionLossLib")
GLOBAL_COUNTER_COMMAND = _server_command("GlobalCounterLib")
OUTPUT_SERVER_COMMAND = _server_command("StdioOutputLib")
# Where StdioOutputLib on the server writes the PID of the child process that keeps running.
CHILD_PID_FILE = os.path.join(tempfile.gettempdir(), "jsonrpcremote-pipe-output-child.pid")
# The pipe of the server that pipe_server.robot starts: a bare name on Windows, and elsewhere a socket file in the
# temp directory, so that no run leaves one in the working directory.
PIPE_SERVER_NAME = (
    "jsonrpcremote-pipe-server"
    if sys.platform == "win32"
    else os.path.join(tempfile.gettempdir(), "jsonrpcremote-pipe-server.sock")
)
# A pipe that nobody listens on.
NOBODY_LISTENS = "jsonrpcremote-nobody-listens"
# The hand-written example server, which connects to the pipe of its --pipe= argument.
OWN_SERVER_COMMAND = shlex.join([sys.executable, "-m", "simple_robot_jsonrpcserver"])
# A server written in Node, and the same server started by a wrapper script, which is a .cmd file on Windows.
NODE_SERVER_COMMAND = shlex.join(["node", os.path.join(_HERE, "node_keywords.js")])
NODE_WRAPPER_COMMAND = shlex.join([os.path.join(_HERE, "node_keywords.cmd")])
