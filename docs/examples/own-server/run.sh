#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# The hand-written server of examples/simple-robot-jsonrpcserver; it listens on 127.0.0.1:8271.
simple-robot-jsonrpcserver &
server=$!
# The example server does not handle SIGTERM, so it ends with the signal's exit status.
trap 'kill "$server"; wait "$server" || true' EXIT
# Wait up to 10 seconds until the server accepts connections.
for _ in $(seq 50); do
    python -c "import socket; socket.create_connection(('127.0.0.1', 8271), 1).close()" 2>/dev/null && break
    sleep 0.2
done

robot echo.robot
