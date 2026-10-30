#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

robot-jsonrpcremote-server --pythonpath . Counter &
server=$!
trap 'kill "$server"; wait "$server"' EXIT
# Wait up to 10 seconds until the server accepts connections.
for _ in $(seq 50); do
    python -c "import socket; socket.create_connection(('127.0.0.1', 8271), 1).close()" 2>/dev/null && break
    sleep 0.2
done

robot counter.robot
