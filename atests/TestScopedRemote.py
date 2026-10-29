"""Test-only client library: JsonRpcRemote with ``rpc_scope`` given as a string from Python.

Robot Framework imports this subclass, not ``JsonRpcRemote``, so it does not convert ``rpc_scope``:
the client gets the string, as from any library built on it.
"""

from JsonRpcRemote import JsonRpcRemote


class TestScopedRemote(JsonRpcRemote):
    def __init__(self, uri: str) -> None:
        super().__init__(uri, "SessionValueLib", rpc_scope="TEST")
