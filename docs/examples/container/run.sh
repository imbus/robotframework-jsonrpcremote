#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Build the wheels of the current code; the image installs them instead of the release on PyPI.
rm -rf wheels
for package in jsonrpcpeer robotframework-jsonrpcremote-protocol robotframework-jsonrpcremote-server; do
    uv build --package "$package" --wheel -o wheels
done
docker build --tag my-library-server --build-arg PACKAGES="/context/wheels/*.whl" .

# Start the server, with its port published on the loopback address of this machine only.
docker run --detach --rm --name my-library-server --publish 127.0.0.1:8271:8271 my-library-server
trap 'docker stop my-library-server' EXIT

# Wait up to 30 seconds until the server in the container is up: the published port accepts
# connections before the server listens.
for _ in $(seq 150); do
    docker logs my-library-server 2>&1 | grep -q "Server is up and running" && break
    sleep 0.2
done

# The suite from Getting started.
robot ../getting-started/greet.robot
