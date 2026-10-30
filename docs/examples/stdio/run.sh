#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# No server to start: the client starts it for the suite and stops it afterwards.
robot greet.robot
