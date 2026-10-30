#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Start the server with MyLibrary in the background; it listens on 127.0.0.1:8271.
robot-jsonrpcremote-server --pythonpath . MyLibrary &
server=$!
# Stop the server when the script ends, also when the suite fails.
trap 'kill "$server"; wait "$server"' EXIT
# Wait up to 10 seconds until the server accepts connections.
for _ in $(seq 50); do
    python -c "import socket; socket.create_connection(('127.0.0.1', 8271), 1).close()" 2>/dev/null && break
    sleep 0.2
done

# Run the suite against the server.
robot greet.robot
