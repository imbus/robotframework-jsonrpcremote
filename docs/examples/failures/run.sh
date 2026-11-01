#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

robot-jsonrpcremote-server --pythonpath . FailingLibrary &
server=$!
trap 'kill "$server"; wait "$server"' EXIT
# Wait up to 10 seconds until the server accepts connections.
for _ in $(seq 50); do
    python -c "import socket; socket.create_connection(('127.0.0.1', 8271), 1).close()" 2>/dev/null && break
    sleep 0.2
done

# The tests fail on purpose, so the exit code tells nothing. Check what the page says about them,
# twice: the server keeps running after the fatal failure.
for _ in 1 2; do
    robot --nostatusrc --loglevel DEBUG failures.robot

    python - <<'CHECK'
from robot.api import ExecutionResult

tests = {test.name: test for test in ExecutionResult("output.xml").suite.all_tests}
results = {name: (test.status, test.message) for name, test in tests.items()}
expected = {
    "Normal Failure": ("FAIL", "ValueError: bad value"),
    "Skipped": ("SKIP", "not today"),
    "Continuable Failure": ("FAIL", "go on"),
    "Fatal Failure": ("FAIL", "FatalError: stop all"),
    "Not Run": ("FAIL", "Test execution stopped due to a fatal error."),
}
assert results == expected, results

normal_failure = tests["Normal Failure"].body
assert normal_failure[1].status == "NOT RUN"
tracebacks = [m.message for m in normal_failure[0].body if m.level == "DEBUG" and "Traceback" in m.message]
assert all(traceback.startswith("[remote] Traceback") for traceback in tracebacks), tracebacks
assert len(tracebacks) == 1, tracebacks
assert 'raise ValueError("bad value")' in tracebacks[0], tracebacks

assert tests["Continuable Failure"].body[1].status == "PASS"
CHECK
done
