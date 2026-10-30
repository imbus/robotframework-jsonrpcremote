#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Start the suite first: its library import waits for the server.
robot greet.robot &
suite=$!

# Start the server a few seconds later, as a container that is still starting would.
sleep 3
robot-jsonrpcremote-server --pythonpath . MyLibrary &
server=$!
trap 'kill "$server"; wait "$server"' EXIT

wait "$suite"
