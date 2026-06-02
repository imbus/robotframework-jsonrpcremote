"""Variables for the stdio transport suites: the ``stdio:<command>`` server commands."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

_BASE = f"{sys.executable} -m robot_jsonrpcremote_server --stdio --pythonpath {_HERE}"

SERVER_COMMAND = f"{_BASE} StdioEchoLib"
PROBE_SERVER_COMMAND = f"{_BASE} ServerProbeLib"
