"""Variables for the stdio transport suite.

Builds the ``stdio:<command>`` server command used by the JsonRpcRemote client to
spawn the server as a subprocess. ``sys.executable`` keeps it tied to the active
interpreter; ``--pythonpath`` makes ``StdioEchoLib`` importable by the server.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

SERVER_COMMAND = f"{sys.executable} -m robot_jsonrpcremote_server --stdio --pythonpath {_HERE} StdioEchoLib"
