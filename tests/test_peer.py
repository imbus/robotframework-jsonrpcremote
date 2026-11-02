import asyncio
import gc
import json
import logging
import warnings
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

import jsonrpcpeer.peer
from jsonrpcpeer import JsonRpcConnectionClosedError, JsonRpcErrorCode, JsonRpcPeer, JsonRpcResponseError, rpc_request
from jsonrpcpeer.peer import (
    JsonRpcErrorResponse,
    JsonRpcMethodAlreadyRegisteredError,
    JsonRpcNotification,
    JsonRpcRequest,
)


@dataclass
class Sum:
    total: int


def make_peer(**options: Any) -> JsonRpcPeer:
    """A peer with a real reader and a dummy writer, for tests that never send."""
    return JsonRpcPeer(asyncio.StreamReader(), MagicMock(), **options)


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


async def _peer_ended_by_read_error(error: Exception) -> JsonRpcPeer:
    reader = asyncio.StreamReader()
    peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", _FakeWriter()))
    peer.start()
    reader.set_exception(error)
    assert peer._read_task is not None
    await asyncio.wait_for(peer._read_task, 2)
    return peer


async def test_read_error_nobody_waits_for_is_not_reported_as_never_retrieved() -> None:
    loop = asyncio.get_running_loop()
    reports: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, context: reports.append(context))
    try:
        await _peer_ended_by_read_error(ConnectionResetError("reset by peer"))

        gc.collect()
        assert not [report for report in reports if "never retrieved" in str(report.get("message"))]
    finally:
        loop.set_exception_handler(None)


async def test_read_error_reaches_a_later_wait_for_the_completion() -> None:
    error = ConnectionResetError("reset by peer")
    peer = await _peer_ended_by_read_error(error)
    await asyncio.sleep(0)

    with pytest.raises(ConnectionResetError) as exc_info:
        await peer.completion
    assert exc_info.value is error


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


# --- lifecycle --------------------------------------------------------------


async def _wait_for_read_loop_end(peer: JsonRpcPeer) -> None:
    await _wait_until(lambda: peer._read_task is not None and peer._read_task.done())


async def test_stopped_peer_is_freed() -> None:
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", _FakeWriter()))
    peer.start()
    await asyncio.sleep(0)
    await peer.stop()
    ref = weakref.ref(peer)
    del peer
    # Until the loop finishes the step that resumed us, it still holds the cancelled read task,
    # whose CancelledError references the peer through its traceback.
    await asyncio.sleep(0)

    gc.collect()

    assert ref() is None


async def test_peer_whose_connection_the_remote_side_closed_is_freed() -> None:
    reader = asyncio.StreamReader()
    peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", _FakeWriter()))
    peer.start()
    reader.feed_eof()
    await asyncio.wait_for(peer.completion, 2)
    await _wait_for_read_loop_end(peer)
    ref = weakref.ref(peer)
    del peer

    gc.collect()

    assert ref() is None


class _EchoEndpoint:
    rpc_peer: JsonRpcPeer | None = None

    @rpc_request("echo")
    async def echo(self, params: Any) -> Any:
        return params


async def test_peer_with_an_attached_endpoint_is_freed_together_with_it() -> None:
    accepted: asyncio.Queue[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = asyncio.Queue()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await accepted.put((reader, writer))

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    try:
        client = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1]))
        peer = JsonRpcPeer(*await asyncio.wait_for(accepted.get(), 2))
        endpoint = _EchoEndpoint()
        peer.attach_endpoint(endpoint)
        client.start()
        peer.start()
        assert await asyncio.wait_for(client.send_request("echo", {"x": 1}), 2) == {"x": 1}

        # The client closes the connection; the peer ends on its own.
        await client.stop()
        await asyncio.wait_for(peer.completion, 2)
        await _wait_for_read_loop_end(peer)
        peer_ref, endpoint_ref = weakref.ref(peer), weakref.ref(endpoint)
        del peer, endpoint

        gc.collect()

        assert peer_ref() is None
        assert endpoint_ref() is None
    finally:
        server.close()
        await server.wait_closed()


async def test_stopping_a_peer_that_was_never_started_ends_it() -> None:
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", _FakeWriter()))

    async with asyncio.timeout(2):
        await peer.stop()

    assert peer.completion.result() is True


async def test_stopping_a_peer_right_after_start_ends_it() -> None:
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", _FakeWriter()))
    peer.start()

    # In the same task, so the read loop does not get to run before the stop.
    async with asyncio.timeout(2):
        await peer.stop()

    assert peer.completion.result() is True


async def test_stopping_a_peer_that_was_never_started_fails_its_waiting_request() -> None:
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", _FakeWriter()))
    request = asyncio.create_task(peer.send_request("ping"))
    await _wait_until(lambda: bool(peer._pending_requests))

    async with asyncio.timeout(2):
        await peer.stop()

    with pytest.raises(JsonRpcConnectionClosedError) as exc_info:
        await asyncio.wait_for(request, 2)
    assert exc_info.value.__cause__ is None


async def test_request_after_stopping_a_peer_that_was_never_started_fails_without_writing() -> None:
    writer = _FakeWriter()
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", writer))
    async with asyncio.timeout(2):
        await peer.stop()

    with pytest.raises(JsonRpcConnectionClosedError):
        await peer.send_request("ping")
    assert writer.written == []


@pytest.mark.parametrize("auto_close", [True, False])
async def test_stopping_a_peer_that_was_never_started_closes_its_writer_only_with_auto_close(
    auto_close: bool,
) -> None:
    writer = _FakeWriter()
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", writer), auto_close=auto_close)

    async with asyncio.timeout(2):
        await peer.stop()

    assert writer.closed is auto_close


class _WriterWithSharedClose(_FakeWriter):
    """A writer whose wait_closed() awaits one future shared by all callers, as StreamWriter does."""

    def __init__(self) -> None:
        super().__init__()
        self.close_done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def wait_closed(self) -> None:
        await self.close_done


async def _peer_waiting_for_its_close() -> tuple[JsonRpcPeer, _WriterWithSharedClose]:
    """A started peer whose read loop ended and now waits in its cleanup for the writer to close."""
    reader = asyncio.StreamReader()
    writer = _WriterWithSharedClose()
    peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", writer))
    peer.start()
    reader.feed_eof()
    await _wait_until(lambda: writer.closed)
    return peer, writer


async def test_stopping_a_peer_does_not_cancel_the_close_that_others_wait_for() -> None:
    peer, writer = await _peer_waiting_for_its_close()
    other = asyncio.create_task(writer.wait_closed())
    await asyncio.sleep(0)

    async with asyncio.timeout(2):
        await peer.stop()

    assert not writer.close_done.cancelled()
    writer.close_done.set_result(None)
    await asyncio.wait_for(other, 2)


async def test_stopping_a_peer_does_not_wait_for_its_writer_to_close() -> None:
    peer, writer = await _peer_waiting_for_its_close()

    async with asyncio.timeout(2):
        await peer.stop()

    assert not writer.close_done.done()
    writer.close_done.set_result(None)


async def test_stopping_a_peer_whose_read_loop_never_ran_does_not_wait_for_its_writer_to_close() -> None:
    writer = _WriterWithSharedClose()
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", writer))

    async with asyncio.timeout(2):
        await peer.stop()

    assert writer.closed
    assert not writer.close_done.done()
    writer.close_done.set_result(None)


async def _peer_whose_read_loop_never_ran() -> tuple[JsonRpcPeer, _WriterWithSharedClose]:
    writer = _WriterWithSharedClose()
    return JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", writer)), writer


@pytest.mark.parametrize("make_peer", [_peer_waiting_for_its_close, _peer_whose_read_loop_never_ran])
async def test_a_close_that_fails_after_the_peer_was_stopped_leaves_no_unretrieved_error(
    make_peer: Callable[[], Awaitable[tuple[JsonRpcPeer, _WriterWithSharedClose]]],
) -> None:
    loop = asyncio.get_running_loop()
    reports: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, context: reports.append(context))
    try:
        peer, writer = await make_peer()
        async with asyncio.timeout(2):
            await peer.stop()
        # asyncio reports an unretrieved error only when its task is collected, together with the peer.
        del peer

        writer.close_done.set_exception(NotImplementedError("write pipe has no close waiter"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        gc.collect()
        assert not [report for report in reports if "never retrieved" in str(report.get("message"))]
    finally:
        loop.set_exception_handler(None)


_Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]


async def _connected_streams() -> tuple[asyncio.Server, _Streams, _Streams]:
    accepted: asyncio.Queue[_Streams] = asyncio.Queue()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await accepted.put((reader, writer))

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    client_streams = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
    return server, client_streams, await asyncio.wait_for(accepted.get(), 2)


def test_peer_can_be_created_without_a_running_event_loop() -> None:
    loop = asyncio.new_event_loop()
    try:
        server, client_streams, server_streams = loop.run_until_complete(_connected_streams())

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            client = JsonRpcPeer(*client_streams)
            remote = JsonRpcPeer(*server_streams)

        async def exchange() -> None:
            async def add(params: Any) -> Any:
                return params["a"] + params["b"]

            remote.register_request_handler("add", add)
            client.start()
            remote.start()
            assert await asyncio.wait_for(client.send_request("add", {"a": 1, "b": 2}), 2) == 3
            await client.stop()
            await remote.stop()
            server.close()
            await server.wait_closed()

        loop.run_until_complete(exchange())
    finally:
        loop.close()


# --- error responses --------------------------------------------------------


def _frame(message: Any) -> bytes:
    body = json.dumps(message).encode()
    return b"Content-Length: %d\r\n\r\n%s" % (len(body), body)


async def _failure_of_waiting_request(response: dict[str, Any]) -> JsonRpcResponseError:
    """The error of a request whose response is `response`, which needs no `jsonrpc` and no `id`."""
    peer, reader, request = await _peer_with_waiting_request()
    reader.feed_data(_frame({"jsonrpc": "2.0", "id": "1", **response}))
    with pytest.raises(JsonRpcResponseError) as exc_info:
        await asyncio.wait_for(request, 2)
    await peer.stop()
    return exc_info.value


async def test_error_response_fails_the_request_with_its_fields() -> None:
    error = await _failure_of_waiting_request(
        {"error": {"code": -32601, "message": "no such method", "data": "details"}}
    )

    assert (error.code, error.message, error.data) == (-32601, "no such method", "details")
    assert str(error) == "RPC Error -32601: no such method"


async def test_error_response_is_no_connection_failure(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair

    async def echo(params: Any) -> Any:
        return params

    server.register_request_handler("echo", echo)

    with pytest.raises(JsonRpcResponseError) as exc_info:
        await asyncio.wait_for(client.send_request("missing"), 2)

    assert not isinstance(exc_info.value, ConnectionError)
    assert await asyncio.wait_for(client.send_request("echo", {"x": 1}), 2) == {"x": 1}


def test_response_error_and_its_codes_are_part_of_the_package_api() -> None:
    assert jsonrpcpeer.JsonRpcResponseError is jsonrpcpeer.peer.JsonRpcResponseError
    assert jsonrpcpeer.JsonRpcErrorCode is jsonrpcpeer.peer.JsonRpcErrorCode


async def test_error_that_is_not_an_object_fails_the_request_with_its_text() -> None:
    error = await _failure_of_waiting_request({"error": "boom"})

    assert (error.code, error.message, error.data) == (-32603, "boom", None)


async def test_response_with_neither_a_result_nor_an_error_fails_the_request() -> None:
    error = await _failure_of_waiting_request({})

    assert error.code == -32603
    assert str(error) == "RPC Error -32603: Invalid response format"


def _errors_of_the_peer(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record for record in caplog.records if record.name == "jsonrpcpeer.peer" and record.levelno >= logging.ERROR
    ]


async def _gone(params: Any) -> Any:
    raise JsonRpcResponseError(-32001, "gone")


async def _gone_with_details(params: Any) -> Any:
    raise JsonRpcResponseError(-32001, "gone", "details")


async def _bad_value(params: Any) -> Any:
    raise ValueError("bad value")


async def _gone_with_data_that_is_no_json(params: Any) -> Any:
    raise JsonRpcResponseError(-32001, "gone", object())


async def _gone_with_a_long_message(params: Any) -> Any:
    raise JsonRpcResponseError(-32001, "gone" * 100)


async def _bad_value_with_a_long_message(params: Any) -> Any:
    raise ValueError("bad value" * 100)


async def _total(params: Sum) -> int:
    return params.total


async def _failure_of_handler(client: JsonRpcPeer, server: JsonRpcPeer, handler: Any) -> JsonRpcResponseError:
    """The error that a client gets from a request answered by `handler`."""
    server.register_request_handler("call", handler)
    with pytest.raises(JsonRpcResponseError) as exc_info:
        await asyncio.wait_for(client.send_request("call"), 2)
    return exc_info.value


async def test_handler_answers_with_the_code_and_the_message_of_its_error(
    peer_pair: tuple[JsonRpcPeer, JsonRpcPeer], caplog: pytest.LogCaptureFixture
) -> None:
    client, server = peer_pair

    error = await _failure_of_handler(client, server, _gone)

    assert (error.code, error.message, error.data) == (-32001, "gone", None)
    assert not _errors_of_the_peer(caplog)


async def test_handler_answers_with_the_data_of_its_error(peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]) -> None:
    client, server = peer_pair

    error = await _failure_of_handler(client, server, _gone_with_details)

    assert error.data == "details"


@pytest.mark.parametrize(
    "handler", [_gone_with_data_that_is_no_json, _gone_with_a_long_message, _bad_value_with_a_long_message]
)
async def test_request_gets_an_answer_when_its_error_response_cannot_be_sent(
    peer_pair: tuple[JsonRpcPeer, JsonRpcPeer], handler: Any
) -> None:
    client, server = peer_pair
    server.max_message_size = 200

    error = await _failure_of_handler(client, server, handler)

    assert error.code == -32603


async def test_unexpected_exception_of_a_handler_has_no_traceback_by_default(
    peer_pair: tuple[JsonRpcPeer, JsonRpcPeer],
) -> None:
    client, server = peer_pair

    error = await _failure_of_handler(client, server, _bad_value)

    assert (error.code, error.message, error.data) == (-32603, "bad value", None)


async def test_params_that_cannot_be_converted_have_no_traceback_by_default_and_are_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    peer = make_peer()
    peer.register_request_handler("add", _total)

    response = await peer.process_request(JsonRpcRequest(method="add", id=1, params={"total": "not-an-int"}))

    assert isinstance(response, JsonRpcErrorResponse)
    assert response.error.code == JsonRpcErrorCode.INVALID_PARAMS
    assert response.error.data is None
    assert not _errors_of_the_peer(caplog)


async def _response_to_a_message_that_cannot_be_parsed(peer: JsonRpcPeer) -> JsonRpcErrorResponse:
    sent: list[Any] = []

    async def capture(message: Any) -> None:
        sent.append(message)

    peer._send_message = capture  # type: ignore[method-assign]
    await peer.handle_message("{not json")
    assert isinstance(sent[0], JsonRpcErrorResponse)
    return sent[0]


async def test_message_that_cannot_be_parsed_has_no_traceback_by_default_and_is_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = await _response_to_a_message_that_cannot_be_parsed(make_peer())

    assert response.error.code == JsonRpcErrorCode.PARSE_ERROR
    assert response.error.data is None
    assert not _errors_of_the_peer(caplog)


async def test_peer_configured_to_send_tracebacks_sends_that_of_a_handler() -> None:
    peer = make_peer(send_tracebacks=True)
    peer.register_request_handler("call", _bad_value)

    response = await peer.process_request(JsonRpcRequest(method="call", id=1))

    assert isinstance(response, JsonRpcErrorResponse)
    assert response.error.code == JsonRpcErrorCode.INTERNAL_ERROR
    assert response.error.message == "bad value"
    assert 'raise ValueError("bad value")' in str(response.error.data)


async def test_peer_configured_to_send_tracebacks_sends_that_of_params_that_cannot_be_converted() -> None:
    peer = make_peer(send_tracebacks=True)
    peer.register_request_handler("add", _total)

    response = await peer.process_request(JsonRpcRequest(method="add", id=1, params={"total": "not-an-int"}))

    assert isinstance(response, JsonRpcErrorResponse)
    assert "Traceback (most recent call last):" in str(response.error.data)


async def test_peer_configured_to_send_tracebacks_sends_that_of_a_message_that_cannot_be_parsed() -> None:
    response = await _response_to_a_message_that_cannot_be_parsed(make_peer(send_tracebacks=True))

    assert "JSONDecodeError" in str(response.error.data)


async def test_peer_configured_to_send_tracebacks_leaves_the_error_of_a_handler_as_it_is() -> None:
    peer = make_peer(send_tracebacks=True)
    peer.register_request_handler("call", _gone)

    response = await peer.process_request(JsonRpcRequest(method="call", id=1))

    assert isinstance(response, JsonRpcErrorResponse)
    assert response.error.data is None


@pytest.mark.parametrize("send_tracebacks", [False, True])
async def test_unexpected_exception_of_a_request_handler_is_logged(
    send_tracebacks: bool, caplog: pytest.LogCaptureFixture
) -> None:
    peer = make_peer(send_tracebacks=send_tracebacks)
    peer.register_request_handler("add", _bad_value)

    await peer.process_request(JsonRpcRequest(method="add", id=1))

    errors = _errors_of_the_peer(caplog)
    assert len(errors) == 1
    assert "'add'" in errors[0].getMessage()
    assert 'raise ValueError("bad value")' in caplog.text


@pytest.mark.parametrize("send_tracebacks", [False, True])
async def test_unexpected_exception_of_a_notification_handler_is_logged(
    send_tracebacks: bool, caplog: pytest.LogCaptureFixture
) -> None:
    peer = make_peer(send_tracebacks=send_tracebacks)
    peer.register_notification_handler("changed", _bad_value)

    await peer.process_notification(JsonRpcNotification(method="changed"))

    errors = _errors_of_the_peer(caplog)
    assert len(errors) == 1
    assert "'changed'" in errors[0].getMessage()
    assert 'raise ValueError("bad value")' in caplog.text


async def test_error_that_a_notification_handler_raises_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    peer = make_peer()
    peer.register_notification_handler("changed", _gone)

    await peer.process_notification(JsonRpcNotification(method="changed"))

    assert not _errors_of_the_peer(caplog)
