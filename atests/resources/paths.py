"""Variables for the folders of the Robot tests, so that a suite finds them from any folder below ``atests``.

``${LIBRARIES}`` holds the libraries that the tests run, on a server or locally, ``${SERVER_ONLY}`` the libraries
that only a server has on its module search path, ``${NESTED}`` the suites of the nested Robot runs, and
``${NODE_EXAMPLE}`` the folder of the example server in Node.js.
"""

import os

__all__ = ["LIBRARIES", "NESTED", "NODE_EXAMPLE", "SERVER_ONLY"]

_ATESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIBRARIES = os.path.join(_ATESTS, "libraries")
SERVER_ONLY = os.path.join(LIBRARIES, "server_only")
NESTED = os.path.join(_ATESTS, "_nested")
NODE_EXAMPLE = os.path.join(os.path.dirname(_ATESTS), "examples", "node-robot-jsonrpcserver")
