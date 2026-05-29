"""Unit tests for the server endpoint's lifecycle handlers (finalize/shutdown/exit).

A stub stands in for ``RobotRemoteContext`` so the handlers can be exercised without a
running Robot suite.
"""

from typing import Any, cast

from robot_jsonrpcremote_protocol import (
    ExitParams,
    FinalizeLibraryParams,
    ImportLibraryParams,
    InitializedParams,
    InitializeParams,
    LibraryDefinition,
    ShutdownParams,
)
from robot_jsonrpcremote_server._endpoint import RobotServerEndpoint
from robot_jsonrpcremote_server._runner import RobotRemoteContext


class _StubContext:
    """Minimal stand-in for RobotRemoteContext recording finalize calls."""

    def __init__(self) -> None:
        self.finalized: list[str] = []

    async def import_library(self, name: str, args: Any, token: str, subscriber: Any = None) -> LibraryDefinition:
        return LibraryDefinition(name=name, keywords=[])

    async def finalize_library(self, token: str, subscriber: Any = None) -> None:
        self.finalized.append(token)


async def _initialized_endpoint(context: _StubContext) -> RobotServerEndpoint:
    endpoint = RobotServerEndpoint(remote_context=cast(RobotRemoteContext, context))
    await endpoint.initialize(InitializeParams())
    await endpoint.initialized(InitializedParams())
    return endpoint


async def test_import_tracks_token_and_finalize_releases_it() -> None:
    context = _StubContext()
    endpoint = await _initialized_endpoint(context)

    result = await endpoint.import_library(ImportLibraryParams(name="Lib"))
    assert result.token in endpoint._imported_tokens

    await endpoint.finalize_library(FinalizeLibraryParams(token=result.token))
    assert result.token not in endpoint._imported_tokens
    assert context.finalized == [result.token]


async def test_shutdown_sets_flag_and_returns_empty_result() -> None:
    endpoint = await _initialized_endpoint(_StubContext())

    result = await endpoint.shutdown(ShutdownParams())

    assert endpoint._shutdown_received is True
    assert result is not None


async def test_finalize_all_releases_remaining_tokens() -> None:
    context = _StubContext()
    endpoint = await _initialized_endpoint(context)
    r1 = await endpoint.import_library(ImportLibraryParams(name="A"))
    r2 = await endpoint.import_library(ImportLibraryParams(name="B"))

    await endpoint.finalize_all()

    assert endpoint._imported_tokens == set()
    assert set(context.finalized) == {r1.token, r2.token}


class _FakeReader:
    def __init__(self) -> None:
        self.eof = False

    def feed_eof(self) -> None:
        self.eof = True


class _FakePeer:
    def __init__(self) -> None:
        self.running = True
        self.reader = _FakeReader()


async def test_exit_closes_connection() -> None:
    endpoint = await _initialized_endpoint(_StubContext())
    peer = _FakePeer()
    endpoint.rpc_peer = cast(Any, peer)

    await endpoint.exit(ExitParams())

    assert peer.running is False
    assert peer.reader.eof is True
