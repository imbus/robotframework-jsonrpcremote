"""A small standalone server over stdio, with only the standard library, as a server in another language would be.

It reads and writes the frames with plain blocking I/O, answers the handshake, offers the keyword
``Echo`` and exits at the end of its input. Tests start it the way the client starts any server.
"""

import json
import sys
from typing import IO, Any

_RESULTS: dict[str, Any] = {
    "robot/initialize": {"capabilities": {"support_exit": True}},
    "robot/import_library": {
        "token": "minimal",
        "definition": {"name": "MinimalLibrary", "keywords": [{"name": "Echo", "args": [{"name": "message"}]}]},
    },
    "robot/finalize_library": {},
    "robot/shutdown": {},
}


def _read_message(stream: IO[bytes]) -> Any:
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        if not line.strip():
            break
        name, _, value = line.decode("ascii").partition(":")
        if name.strip().lower() == "content-length":
            length = int(value)
    if length is None:
        return None
    return json.loads(stream.read(length))


def _write_message(stream: IO[bytes], message: dict[str, Any]) -> None:
    body = json.dumps({"jsonrpc": "2.0", **message}).encode()
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    stream.flush()


def main() -> None:
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while (message := _read_message(stdin)) is not None:
        method = message.get("method")
        if method == "robot/exit":
            return
        if "id" not in message:
            continue
        if method == "robot/run_keyword":
            _write_message(stdout, {"id": message["id"], "result": {"result": message["params"]["args"][0]}})
        elif method in _RESULTS:
            _write_message(stdout, {"id": message["id"], "result": _RESULTS[method]})
        else:
            error = {"code": -32601, "message": f"Method '{method}' not found."}
            _write_message(stdout, {"id": message["id"], "error": error})


if __name__ == "__main__":
    main()
