"""The example server in Node.js, for the tests that run it: its folder, and ``node`` or a skip."""

import os
import shutil
from pathlib import Path

import pytest

NODE_EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "node-robot-jsonrpcserver"


def node_or_skip(path: str | None = None) -> str:
    """The path of ``node`` on ``path``, by default on PATH, if it and the packages of the example are installed.

    Without them, the test skips, except in CI, which installs them, where it fails.
    """
    found = shutil.which("node", path=path)
    if found is None:
        missing = "node is not installed"
    elif not (NODE_EXAMPLE / "node_modules" / "vscode-jsonrpc").is_dir():
        missing = "the packages of the example are not installed: run npm ci in examples/node-robot-jsonrpcserver"
    else:
        return found
    if os.environ.get("CI"):
        pytest.fail(f"{missing}, and CI installs them")
    pytest.skip(missing)
