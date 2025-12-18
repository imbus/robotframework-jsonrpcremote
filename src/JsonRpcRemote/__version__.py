import importlib

try:
    __version__ = importlib.metadata.version("robotframework-jsonrpcremote")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"
