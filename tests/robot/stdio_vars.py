"""Variables for the stdio transport suite.

Builds the ``stdio:<command>`` server command used by the JsonRpcRemote client to
spawn the server as a subprocess. ``sys.executable`` keeps it tied to the active
interpreter; ``--pythonpath`` makes ``StdioEchoLib`` importable by the server.
"""

import os
import sys

# Exposed so the Windows-only suite can self-skip on POSIX (where stdio works).
IS_WINDOWS = sys.platform == "win32"

_HERE = os.path.dirname(os.path.abspath(__file__))

_BASE = f"{sys.executable} -m robot_jsonrpcremote_server --stdio --pythonpath {_HERE}"

SERVER_COMMAND = f"{_BASE} StdioEchoLib"
PROBE_SERVER_COMMAND = f"{_BASE} ServerProbeLib"
