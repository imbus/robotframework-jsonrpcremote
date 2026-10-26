import asyncio
import gc
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from jsonrpcpeer import JsonRpcConnectionClosedError, JsonRpcPeer
from jsonrpcpeer.peer import (
    JsonRpcErrorCode,
    JsonRpcErrorResponse,
    JsonRpcMethodAlreadyRegisteredError,
    JsonRpcRequest,
)


@dataclass
class Sum:
    total: int


def make_peer() -> JsonRpcPeer:
    """A peer with a real reader and a dummy writer, for tests that never send."""
    return JsonRpcPeer(asyncio.StreamReader(), MagicMock())


@pytest_asyncio.fixture
async def peer_pair() -> AsyncIterator[tuple[JsonRpcPeer, JsonRpcPeer]]:
    """Two peers connected over a loopback TCP socket, both started."""
    holder: dict[str, Any] = {}
    ready = asyncio.Event()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        holder["reader"], holder["writer"] = reader, writer
        ready.set()

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client_reader, client_writer = await asyncio.open_connection("127.0.0.1", port)
    await asyncio.wait_for(ready.wait(), 2)

    client = JsonRpcPeer(client_reader, client_writer)
    server_peer = JsonRpcPeer(holder["reader"], holder["writer"])
    client.start()
    server_peer.start()
    try:
        yield client, server_peer
    finally:
        await client.stop()
        await server_peer.stop()
        server.close()
        await server.wait_closed()


# --- round-trips over a real connection ------------------------------------


async def test_request_response_roundtrip(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair

    async def echo(params: Any) -> Any:
        return params

    server.register_request_handler("echo", echo)
    payload = {"a": 1, "b": [3, 1, 1, 2]}
    result = await asyncio.wait_for(client.send_request("echo", payload), 2)
    assert result == payload  # order and duplicates preserved over the wire


async def test_typed_response(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair

    async def add(params: Any) -> Any:
        return {"total": params["a"] + params["b"]}

    server.register_request_handler("add", add)
    result = await asyncio.wait_for(client.send_request_typed(Sum, "add", {"a": 2, "b": 3}), 2)
    assert result == Sum(total=5)


async def test_notification_roundtrip(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair
    received: asyncio.Future[Any] = asyncio.get_event_loop().create_future()

    async def on_note(params: Any) -> None:
        received.set_result(params)

    server.register_notification_handler("note", on_note)
    await client.send_notification("note", {"x": 1})
    assert await asyncio.wait_for(received, 2) == {"x": 1}


async def test_method_not_found(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, _server = peer_pair
    with pytest.raises(Exception, match="not found"):
        await asyncio.wait_for(client.send_request("missing", {}), 2)


async def test_handler_exception_propagates(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair

    async def boom(params: Any) -> Any:
        raise ValueError("kaboom")

    server.register_request_handler("boom", boom)
    with pytest.raises(Exception, match="kaboom"):
        await asyncio.wait_for(client.send_request("boom", {}), 2)


# --- handler registration / signature validation ---------------------------


async def test_register_duplicate_raises() -> None:
    peer = make_peer()

    async def handler(params: Any) -> Any:
        return params

    peer.register_request_handler("m", handler)
    with pytest.raises(JsonRpcMethodAlreadyRegisteredError):
        peer.register_request_handler("m", handler)


async def test_register_blank_name_raises() -> None:
    peer = make_peer()

    async def handler(params: Any) -> Any:
        return params

    with pytest.raises(ValueError, match="whitespace"):
        peer.register_request_handler("   ", handler)


async def test_two_param_handler_requires_peer_first() -> None:
    peer = make_peer()

    async def bad(not_peer: int, params: Any) -> Any:
        return params

    with pytest.raises(ValueError, match="JsonRpcPeer"):
        peer.register_request_handler("bad", bad)  # type: ignore[arg-type]


async def test_zero_param_handler_invalid() -> None:
    peer = make_peer()

    async def zero() -> None:
        return None

    with pytest.raises(ValueError, match="signature"):
        peer.register_request_handler("zero", zero)  # type: ignore[arg-type]


async def test_two_param_handler_with_peer_ok() -> None:
    peer = make_peer()

    async def good(p: JsonRpcPeer, params: Any) -> Any:
        return params

    peer.register_request_handler("good", good)  # must not raise


# --- malformed message handling --------------------------------------------


async def test_invalid_jsonrpc_version() -> None:
    peer = make_peer()
    resp = await peer.process_single_message({"jsonrpc": "1.0", "id": 1, "method": "x"})
    assert isinstance(resp, JsonRpcErrorResponse)
    assert resp.error.code == JsonRpcErrorCode.INVALID_REQUEST


async def test_non_dict_payload() -> None:
    peer = make_peer()
    resp = await peer.process_single_message("not-a-dict")
    assert isinstance(resp, JsonRpcErrorResponse)
    assert resp.error.code == JsonRpcErrorCode.INVALID_REQUEST


# --- malformed batch / extra fields (N1, N2) --------------------------------


async def test_empty_batch_returns_error() -> None:
    peer = make_peer()
    sent: list[Any] = []

    async def capture(msg: Any) -> None:
        sent.append(msg)

    peer._send_message = capture  # type: ignore[method-assign, assignment]
    await peer.handle_message("[]")
    assert len(sent) == 1
    assert isinstance(sent[0], JsonRpcErrorResponse)
    assert sent[0].error.code == JsonRpcErrorCode.INVALID_REQUEST


async def test_request_with_extra_field_error_code() -> None:
    peer = make_peer()
    sent: list[Any] = []

    async def capture(msg: Any) -> None:
        sent.append(msg)

    peer._send_message = capture  # type: ignore[method-assign, assignment]
    await peer.handle_message(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "x", "extra": 1}))
    assert len(sent) == 1
    assert isinstance(sent[0], JsonRpcErrorResponse)
    assert sent[0].error.code != JsonRpcErrorCode.INTERNAL_ERROR


async def test_malformed_error_response_resolves_pending_request() -> None:
    # A non-dict "error" payload must not raise and leave the caller hanging.
    peer = make_peer()
    pending: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
    peer._pending_requests["1"] = pending

    await peer._handle_response({"jsonrpc": "2.0", "id": "1", "error": "boom"}, "1")

    assert pending.done()
    with pytest.raises(Exception, match="boom"):
        pending.result()


async def test_param_conversion_failure_is_invalid_params() -> None:
    # A handler whose typed params cannot be built from the payload yields -32602.
    peer = make_peer()

    async def add(params: Sum) -> int:
        return params.total

    peer.register_request_handler("add", add)
    resp = await peer.process_request(JsonRpcRequest(method="add", id=1, params={"total": "not-an-int"}))
    assert isinstance(resp, JsonRpcErrorResponse)
    assert resp.error.code == JsonRpcErrorCode.INVALID_PARAMS


# --- auto-close cleanup robustness (stdio write pipe) -----------------------


class _WriterWithoutCloseWaiter:
    """A writer whose wait_closed() raises, like the asyncio stdout write pipe."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def is_closing(self) -> bool:
        return self.closed

    async def wait_closed(self) -> None:
        raise NotImplementedError("write pipe has no close waiter")


async def test_io_loop_suppresses_wait_closed_errors() -> None:
    reader = asyncio.StreamReader()
    reader.feed_eof()
    writer = _WriterWithoutCloseWaiter()

    peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", writer))
    await asyncio.wait_for(peer.run(), 2)

    assert peer._read_task is not None
    await asyncio.wait_for(peer._read_task, 2)
    assert peer._read_task.exception() is None
    assert writer.closed


# --- requests around a closed connection ------------------------------------


def test_connection_closed_error_is_a_connection_error() -> None:
    # Exported from the package root (see the import above) and catchable like any transport failure.
    assert issubclass(JsonRpcConnectionClosedError, ConnectionError)


async def _never_answer(params: Any) -> None:
    await asyncio.Event().wait()


async def _wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        assert loop.time() < deadline, "condition not met in time"
        await asyncio.sleep(0.01)


async def test_pending_request_fails_when_remote_closes(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair
    server.register_request_handler("hang", _never_answer)
    request = asyncio.create_task(client.send_request("hang"))
    await _wait_until(lambda: len(server._inflight) == 1)

    server.writer.close()

    with pytest.raises(JsonRpcConnectionClosedError, match="before a response") as exc_info:
        await asyncio.wait_for(request, 2)
    assert exc_info.value.__cause__ is None
    assert not client._pending_requests


async def test_pending_request_fails_when_peer_stops(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair
    server.register_request_handler("hang", _never_answer)
    request = asyncio.create_task(client.send_request("hang"))
    await _wait_until(lambda: len(server._inflight) == 1)

    await client.stop()

    with pytest.raises(JsonRpcConnectionClosedError) as exc_info:
        await asyncio.wait_for(request, 2)
    assert exc_info.value.__cause__ is None


async def test_all_pending_requests_fail_when_remote_closes(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair
    server.register_request_handler("hang", _never_answer)
    requests = [asyncio.create_task(client.send_request("hang")) for _ in range(3)]
    await _wait_until(lambda: len(server._inflight) == 3)

    server.writer.close()

    results = await asyncio.wait_for(asyncio.gather(*requests, return_exceptions=True), 2)
    assert all(isinstance(result, JsonRpcConnectionClosedError) for result in results)


async def test_close_fails_pending_request_before_its_timeout(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair
    client.request_timeout = 5
    server.register_request_handler("hang", _never_answer)
    request = asyncio.create_task(client.send_request("hang"))
    await _wait_until(lambda: len(server._inflight) == 1)

    server.writer.close()

    # Well below the request timeout: the close must not wait for it.
    with pytest.raises(JsonRpcConnectionClosedError):
        await asyncio.wait_for(request, 1)


class _FakeWriter:
    """A writer that accepts every write, for peers whose reader the test feeds by hand."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: Any) -> None:
        self.written.append(bytes(data))

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def is_closing(self) -> bool:
        return self.closed

    async def wait_closed(self) -> None:
        pass


async def _peer_with_waiting_request(
    **options: Any,
) -> tuple[JsonRpcPeer, asyncio.StreamReader, "asyncio.Task[Any]"]:
    """A started peer on a hand-fed reader, with one request waiting for its response."""
    reader = asyncio.StreamReader()
    peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", _FakeWriter()), **options)
    peer.start()
    request = asyncio.create_task(peer.send_request("ping"))
    await _wait_until(lambda: bool(peer._pending_requests))
    return peer, reader, request


async def test_read_error_is_the_cause_of_the_failed_request() -> None:
    peer, reader, request = await _peer_with_waiting_request()
    error = ConnectionResetError("reset by peer")

    reader.set_exception(error)

    with pytest.raises(JsonRpcConnectionClosedError) as exc_info:
        await asyncio.wait_for(request, 2)
    assert exc_info.value.__cause__ is error
    with pytest.raises(ConnectionResetError):
        await peer.completion


async def test_truncated_frame_is_the_cause_of_the_failed_request() -> None:
    peer, reader, request = await _peer_with_waiting_request()

    reader.feed_data(b"Content-Length: 10\r\n\r\n123")
    reader.feed_eof()

    with pytest.raises(JsonRpcConnectionClosedError) as exc_info:
        await asyncio.wait_for(request, 2)
    assert isinstance(exc_info.value.__cause__, asyncio.IncompleteReadError)
    with pytest.raises(asyncio.IncompleteReadError):
        await peer.completion


async def test_oversized_incoming_message_fails_the_request_without_a_cause() -> None:
    _, reader, request = await _peer_with_waiting_request(max_message_size=200)

    reader.feed_data(b"Content-Length: 1000\r\n\r\n")

    with pytest.raises(JsonRpcConnectionClosedError) as exc_info:
        await asyncio.wait_for(request, 2)
    assert exc_info.value.__cause__ is None


async def test_request_after_close_fails_without_writing() -> None:
    reader = asyncio.StreamReader()
    reader.feed_eof()
    writer = MagicMock()
    peer = JsonRpcPeer(reader, writer, auto_close=False)
    await asyncio.wait_for(peer.run(), 2)

    with pytest.raises(JsonRpcConnectionClosedError, match="'ping'"):
        await peer.send_request("ping")
    writer.write.assert_not_called()


class _WriterLostWhileDraining(_FakeWriter):
    """A writer whose drain() lets the loop run and then fails, like a connection lost mid-write."""

    async def drain(self) -> None:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        raise ConnectionResetError("Connection lost")


async def test_close_while_sending_reports_the_closed_connection() -> None:
    loop = asyncio.get_running_loop()
    reports: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, context: reports.append(context))
    try:
        reader = asyncio.StreamReader()
        reader.feed_eof()
        peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", _WriterLostWhileDraining()))
        peer.start()

        # drain() yields: the read loop hits EOF and fails the request, then the write fails.
        with pytest.raises(JsonRpcConnectionClosedError):
            await peer.send_request("ping")

        gc.collect()
        assert not [report for report in reports if "never retrieved" in str(report.get("message"))]
    finally:
        loop.set_exception_handler(None)


async def test_write_error_unrelated_to_a_close_propagates_unchanged() -> None:
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", _FakeWriter()), max_message_size=10)

    with pytest.raises(ValueError, match="exceeds maximum"):
        await peer.send_request("ping")
    assert not peer._closed
    assert not peer._pending_requests
