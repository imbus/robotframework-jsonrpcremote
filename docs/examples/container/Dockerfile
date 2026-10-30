FROM python:3.13-slim

# What pip installs: the server from PyPI by default. The CI of the documentation
# passes the wheels of the current code instead, from the build context.
ARG PACKAGES=robotframework-jsonrpcremote-server
RUN --mount=type=bind,target=/context pip install --no-cache-dir ${PACKAGES}

WORKDIR /libraries
COPY MyLibrary.py .

# All interfaces of the container: connections from outside the container do not
# arrive on its loopback address. `docker run --publish` decides who can connect.
EXPOSE 8271
CMD ["robot-jsonrpcremote-server", "--bind", "0.0.0.0", "--pythonpath", "/libraries", "MyLibrary"]
