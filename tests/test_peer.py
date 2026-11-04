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
from jsonrpcpeer import (
    JsonRpcConnectionClosedError,
    JsonRpcErrorCode,
    JsonRpcPeer,
    JsonRpcResponseError,
    rpc_notification,
    rpc_request,
)
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
    raw = await _start_raw_peer()

    answers = await raw.answers_to(_raw_frame("[]"))
    await raw.peer.stop()

    assert len(answers) == 1
    assert answers[0]["id"] is None
    assert answers[0]["error"]["code"] == JsonRpcErrorCode.INVALID_REQUEST


async def test_request_with_extra_field_error_code() -> None:
    raw = await _start_raw_peer()

    answers = await raw.answers_to(_raw_frame(_rpc(id=1, method="x", extra=1)))
    await raw.peer.stop()

    assert len(answers) == 1
    assert answers[0]["id"] == 1
    assert answers[0]["error"]["code"] == JsonRpcErrorCode.METHOD_NOT_FOUND


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


async def _answer_to_a_message_that_cannot_be_parsed(**options: Any) -> dict[str, Any]:
    raw = await _start_raw_peer(**options)
    answers = await raw.answers_to(_raw_frame("{not json"))
    await raw.peer.stop()
    assert len(answers) == 1
    return cast("dict[str, Any]", answers[0])


async def test_message_that_cannot_be_parsed_has_no_traceback_by_default_and_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    answer = await _answer_to_a_message_that_cannot_be_parsed()

    assert answer["error"]["code"] == JsonRpcErrorCode.PARSE_ERROR
    assert "data" not in answer["error"]
    assert len(_errors_of_the_peer(caplog)) == 1


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
    answer = await _answer_to_a_message_that_cannot_be_parsed(send_tracebacks=True)

    assert "JSONDecodeError" in answer["error"]["data"]


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


# --- reading messages from a raw stream -------------------------------------


def _rpc(**members: Any) -> str:
    return json.dumps({"jsonrpc": "2.0", **members})


def _raw_frame(content: str | bytes, *fields: str) -> bytes:
    """A frame with the header fields ``fields``, by default the right length; ``{n}`` stands for the length."""
    body = content.encode() if isinstance(content, str) else content
    header = "".join(f"{field}\r\n" for field in fields or ("Content-Length: {n}",))
    return header.replace("{n}", str(len(body))).encode("latin-1") + b"\r\n" + body


_CHECK_PARAMS = {"checked": True}
_CHECK = _raw_frame(_rpc(id="check", method="echo", params=_CHECK_PARAMS))


@dataclass
class _RawPeer:
    """A started peer whose reader the test feeds, with what it wrote, reported and called."""

    peer: JsonRpcPeer
    reader: asyncio.StreamReader
    writer: _FakeWriter
    problems: list[str]
    calls: list[tuple[str, Any]]

    def _answers_since(self, start: int) -> list[Any]:
        data = b"".join(self.writer.written[start:])
        answers = []
        while data:
            head, _, rest = data.partition(b"\r\n\r\n")
            length = int(head.split(b":")[1].split(b"\r\n")[0])
            answers.append(json.loads(rest[:length]))
            data = rest[length:]
        return answers

    async def answers_to(self, data: bytes) -> list[Any]:
        """Feed ``data`` and a request behind it. Returns what the peer wrote before it answered that request."""
        start = len(self.writer.written)
        self.reader.feed_data(data + _CHECK)

        def is_answered(answer: Any) -> bool:
            return isinstance(answer, dict) and answer.get("id") == "check"

        await _wait_until(lambda: any(is_answered(answer) for answer in self._answers_since(start)))
        self.calls.remove(("echo", _CHECK_PARAMS))
        return [answer for answer in self._answers_since(start) if not is_answered(answer)]


async def _start_raw_peer(**options: Any) -> _RawPeer:
    reader = asyncio.StreamReader()
    writer = _FakeWriter()
    problems: list[str] = []
    calls: list[tuple[str, Any]] = []
    options.setdefault("on_problem", problems.append)
    peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", writer), **options)

    async def echo(params: Any) -> Any:
        calls.append(("echo", params))
        return params

    async def changed(params: Any) -> None:
        calls.append(("changed", params))

    peer.register_request_handler("echo", echo)
    peer.register_notification_handler("changed", changed)
    peer.start()
    return _RawPeer(peer, reader, writer, problems, calls)


@pytest_asyncio.fixture
async def raw_peer() -> AsyncIterator[_RawPeer]:
    raw = await _start_raw_peer()
    yield raw
    await raw.peer.stop()


async def _waiting_request_of(raw: _RawPeer) -> "asyncio.Task[Any]":
    request = asyncio.create_task(raw.peer.send_request("ping"))
    await _wait_until(lambda: "1" in raw.peer._pending_requests)
    return request


async def _request_gets_its_response_after(raw: _RawPeer, data: bytes) -> None:
    """Pins that the request waits on after ``data``, and that it gets its response when that arrives."""
    request = await _waiting_request_of(raw)
    await raw.answers_to(data)
    assert not request.done()

    raw.reader.feed_data(_raw_frame(_rpc(id="1", result=5)))

    assert await asyncio.wait_for(request, 2) == 5


_REQUEST = _rpc(id=1, method="echo", params={"a": 1})
_ANSWER = {"jsonrpc": "2.0", "id": 1, "result": {"a": 1}}


@pytest.mark.parametrize("value", ["abc", "-5", "+5", "1.5", "1_000", "", "9" * 5000])
async def test_invalid_length_is_reported_and_not_answered(raw_peer: _RawPeer, value: str) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_REQUEST, f"Content-Length: {value}") + b"\r\n")

    assert answers == []
    assert raw_peer.calls == []
    assert len(raw_peer.problems) == 1
    assert repr(value[:100]) in raw_peer.problems[0]


async def test_missing_length_is_reported_and_not_answered(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_REQUEST, "Content-Type: application/json") + b"\r\n")

    assert answers == []
    assert len(raw_peer.problems) == 1
    assert "Content-Length" in raw_peer.problems[0]


async def test_empty_line_between_two_messages(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_REQUEST) + b"\r\n")

    assert answers == [_ANSWER]
    assert len(raw_peer.problems) == 1
    assert "Content-Length" in raw_peer.problems[0]


async def test_waiting_request_survives_an_invalid_length(raw_peer: _RawPeer) -> None:
    await _request_gets_its_response_after(raw_peer, _raw_frame(_REQUEST, "Content-Length: abc") + b"\r\n")


async def test_message_after_content_with_a_line_end_is_handled(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_REQUEST, "Content-Length: abc") + b"\r\n" + _raw_frame(_REQUEST))

    assert answers == [_ANSWER]
    assert len(raw_peer.problems) == 1


async def test_message_after_content_without_a_line_end_is_reported(raw_peer: _RawPeer) -> None:
    raw_peer.reader.feed_data(_raw_frame(_REQUEST, "Content-Length: abc") + _raw_frame(_REQUEST))

    await _wait_until(lambda: len(raw_peer.problems) == 2)
    assert "Content-Length" in raw_peer.problems[1]
    assert raw_peer.writer.written == []
    assert raw_peer.calls == []

    # The connection stays open: the content that is left ends with this line end.
    assert await raw_peer.answers_to(b"\r\n") == []


async def test_problem_is_logged_without_a_callback(caplog: pytest.LogCaptureFixture) -> None:
    raw = await _start_raw_peer(on_problem=None)

    await raw.answers_to(_raw_frame(_REQUEST, "Content-Length: abc") + b"\r\n")
    await raw.peer.stop()

    errors = _errors_of_the_peer(caplog)
    assert len(errors) == 1
    assert "'abc'" in errors[0].getMessage()


async def test_problem_goes_to_the_callback_and_the_log(raw_peer: _RawPeer, caplog: pytest.LogCaptureFixture) -> None:
    await raw_peer.answers_to(_raw_frame(_REQUEST, "Content-Length: abc") + b"\r\n")

    assert "'abc'" in raw_peer.problems[0]
    assert [record.getMessage() for record in _errors_of_the_peer(caplog)] == raw_peer.problems


async def test_exception_of_the_callback_is_logged_and_reading_goes_on(caplog: pytest.LogCaptureFixture) -> None:
    def fail(problem: str) -> None:
        raise ValueError("the callback failed")

    raw = await _start_raw_peer(on_problem=fail)

    assert await raw.answers_to(_raw_frame(_REQUEST, "Content-Length: abc") + b"\r\n") == []
    await raw.peer.stop()

    assert "the callback failed" in caplog.text
    assert len(_errors_of_the_peer(caplog)) == 2


async def test_error_of_a_request_handler_is_no_problem_with_a_message(raw_peer: _RawPeer) -> None:
    raw_peer.peer.register_request_handler("failing", _gone)

    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=1, method="failing", params={})))

    assert answers[0]["error"]["code"] == -32001
    assert raw_peer.problems == []


# --- header fields ----------------------------------------------------------


@pytest.mark.parametrize("name", ["content-length", "CONTENT-LENGTH"])
async def test_header_name_is_matched_without_regard_to_case(raw_peer: _RawPeer, name: str) -> None:
    assert await raw_peer.answers_to(_raw_frame(_REQUEST, f"{name}: {{n}}")) == [_ANSWER]
    assert raw_peer.problems == []


async def test_space_after_the_colon_is_optional(raw_peer: _RawPeer) -> None:
    assert await raw_peer.answers_to(_raw_frame(_REQUEST, "Content-Length:{n}")) == [_ANSWER]
    assert raw_peer.problems == []


async def test_whitespace_around_the_value_is_ignored(raw_peer: _RawPeer) -> None:
    assert await raw_peer.answers_to(_raw_frame(_REQUEST, "Content-Length:   {n}  ")) == [_ANSWER]
    assert raw_peer.problems == []


async def test_charset_with_a_different_spelling(raw_peer: _RawPeer) -> None:
    content = _rpc(id=1, method="echo", params={"a": "ä"}).replace("\\u00e4", "ä").encode("latin-1")

    answers = await raw_peer.answers_to(
        _raw_frame(content, 'content-type: application/json; Charset="latin-1"', "Content-Length: {n}")
    )

    assert answers == [{"jsonrpc": "2.0", "id": 1, "result": {"a": "ä"}}]


@pytest.mark.parametrize("field", ["X-Note: anything", "no colon here"])
async def test_header_field_that_the_peer_does_not_know_is_ignored(raw_peer: _RawPeer, field: str) -> None:
    assert await raw_peer.answers_to(_raw_frame(_REQUEST, field, "Content-Length: {n}")) == [_ANSWER]
    assert raw_peer.problems == []


async def test_byte_outside_ascii_in_an_unknown_header_field(raw_peer: _RawPeer) -> None:
    assert await raw_peer.answers_to(_raw_frame(_REQUEST, "X-Note: caf\xe9", "Content-Length: {n}")) == [_ANSWER]
    assert raw_peer.problems == []


async def test_long_content_without_a_line_end_keeps_the_connection_open(raw_peer: _RawPeer) -> None:
    long_content = "x" * 200_000

    assert await raw_peer.answers_to(_raw_frame(long_content, "Content-Length: abc") + b"\r\n") == []
    assert len(raw_peer.problems) == 1


@pytest.mark.parametrize("length_comes_first", [True, False])
async def test_long_unknown_field_before_and_after_the_length(raw_peer: _RawPeer, length_comes_first: bool) -> None:
    fields = ["Content-Length: {n}", "X-Long: " + "y" * 200_000]

    answers = await raw_peer.answers_to(_raw_frame(_REQUEST, *(fields if length_comes_first else reversed(fields))))

    assert answers == [_ANSWER]
    assert raw_peer.problems == []


# --- content that cannot be read --------------------------------------------


@pytest.mark.parametrize("charset", ["nope", "hex", "a\0b"])
async def test_charset_that_cannot_be_used_is_answered_with_a_parse_error(raw_peer: _RawPeer, charset: str) -> None:
    content_type = f"Content-Type: application/json; charset={charset}"

    answers = await raw_peer.answers_to(_raw_frame(_REQUEST, "Content-Length: {n}", content_type))

    assert len(answers) == 1
    assert answers[0]["id"] is None
    assert answers[0]["error"]["code"] == JsonRpcErrorCode.PARSE_ERROR
    assert repr(charset) in answers[0]["error"]["message"]
    assert raw_peer.problems == [answers[0]["error"]["message"]]
    assert raw_peer.calls == []


async def test_content_not_valid_in_its_charset_is_answered_with_a_parse_error(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_REQUEST.encode() + b"\xff"))

    assert len(answers) == 1
    assert answers[0]["id"] is None
    assert answers[0]["error"]["code"] == JsonRpcErrorCode.PARSE_ERROR
    assert len(raw_peer.problems) == 1


@pytest.mark.parametrize(
    "content", ["{not json", "[" * 200_000, "1" * 5000, ""], ids=["no JSON", "deep nesting", "huge integer", "empty"]
)
async def test_content_that_is_not_json_is_answered_with_a_parse_error(raw_peer: _RawPeer, content: str) -> None:
    answers = await raw_peer.answers_to(_raw_frame(content))

    assert len(answers) == 1
    assert answers[0]["id"] is None
    assert answers[0]["error"]["code"] == JsonRpcErrorCode.PARSE_ERROR
    assert len(raw_peer.problems) == 1


@pytest.mark.parametrize("charset", ["latin-1", "utf8"])
async def test_other_text_encoding_is_decoded(raw_peer: _RawPeer, charset: str) -> None:
    content = _rpc(id=1, method="echo", params={"a": "ä"}).replace("\\u00e4", "ä").encode(charset)
    content_type = f"Content-Type: application/json; charset={charset}"

    answers = await raw_peer.answers_to(_raw_frame(content, "Content-Length: {n}", content_type))

    assert answers == [{"jsonrpc": "2.0", "id": 1, "result": {"a": "ä"}}]
    assert raw_peer.problems == []


async def test_waiting_request_survives_content_that_cannot_be_read(raw_peer: _RawPeer) -> None:
    await _request_gets_its_response_after(raw_peer, _raw_frame("{not json"))


# --- the size limit ---------------------------------------------------------


async def test_message_above_the_limit_is_skipped_and_answered() -> None:
    raw = await _start_raw_peer(max_message_size=200)

    answers = await raw.answers_to(_raw_frame("x" * 1000))
    await raw.peer.stop()

    assert answers == [
        {
            "jsonrpc": "2.0",
            "error": {"code": JsonRpcErrorCode.INVALID_REQUEST, "message": "Message size 1000 exceeds maximum 200"},
            "id": None,
        }
    ]
    assert raw.problems == ["Message size 1000 exceeds maximum 200"]
    assert raw.calls == []


async def test_content_above_the_limit_in_several_parts_is_skipped() -> None:
    raw = await _start_raw_peer(max_message_size=200)
    part = b"x" * 100_000
    raw.reader.feed_data(b"Content-Length: 300000\r\n\r\n" + part)

    for _ in range(2):
        await asyncio.sleep(0)
        raw.reader.feed_data(part)

    answers = await raw.answers_to(b"")
    await raw.peer.stop()

    assert len(answers) == 0
    assert raw.problems == ["Message size 300000 exceeds maximum 200"]


async def test_waiting_request_survives_a_message_above_the_limit() -> None:
    raw = await _start_raw_peer(max_message_size=200)

    await _request_gets_its_response_after(raw, _raw_frame("x" * 1000))
    await raw.peer.stop()


# --- telling messages apart -------------------------------------------------


def _codes_and_ids(answers: list[Any]) -> list[tuple[int, Any]]:
    return [(answer["error"]["code"], answer["id"]) for answer in answers]


@pytest.mark.parametrize("members", [{}, {"params": {}}], ids=["nothing", "only params"])
async def test_message_with_neither_a_method_nor_an_id_is_invalid(raw_peer: _RawPeer, members: dict[str, Any]) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(**members)))

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INVALID_REQUEST, None)]
    assert len(raw_peer.problems) == 1


async def test_method_that_is_no_string_is_invalid(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=1, method=[])) + _raw_frame(_rpc(method=1, params="bar")))

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INVALID_REQUEST, 1), (JsonRpcErrorCode.INVALID_REQUEST, None)]
    assert len(raw_peer.problems) == 2


@pytest.mark.parametrize("params", ["bar", 5, True], ids=["string", "number", "boolean"])
async def test_params_that_are_neither_an_array_nor_an_object_are_invalid(raw_peer: _RawPeer, params: Any) -> None:
    answers = await raw_peer.answers_to(
        _raw_frame(_rpc(id=1, method="echo", params=params)) + _raw_frame(_rpc(method="changed", params=params))
    )

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INVALID_REQUEST, 1), (JsonRpcErrorCode.INVALID_REQUEST, None)]
    assert raw_peer.calls == []
    assert len(raw_peer.problems) == 2


async def test_array_as_params_reaches_the_handler(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=1, method="echo", params=[1, 2])))

    assert answers == [{"jsonrpc": "2.0", "id": 1, "result": [1, 2]}]
    assert raw_peer.calls == [("echo", [1, 2])]


async def test_null_params_count_as_missing(raw_peer: _RawPeer) -> None:
    await raw_peer.answers_to(
        _raw_frame(_rpc(id=1, method="echo", params=None)) + _raw_frame(_rpc(id=2, method="echo"))
    )

    assert raw_peer.calls == [("echo", None), ("echo", None)]
    assert raw_peer.problems == []


@pytest.mark.parametrize("id_value", [{"a": 1}, True, 1.5], ids=["object", "true", "fraction"])
async def test_id_of_another_type_is_invalid(raw_peer: _RawPeer, id_value: Any) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=id_value, method="echo", params={})))

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INVALID_REQUEST, None)]
    assert raw_peer.calls == []
    assert len(raw_peer.problems) == 1


async def test_null_id_with_a_method_is_invalid(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=None, method="echo", params={})))

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INVALID_REQUEST, None)]
    assert raw_peer.calls == []


async def test_message_that_is_no_object_is_invalid(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame("1"))

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INVALID_REQUEST, None)]
    assert len(raw_peer.problems) == 1


@pytest.mark.parametrize("version", [{}, {"jsonrpc": "1.0"}], ids=["missing", "1.0"])
async def test_other_version_is_invalid(raw_peer: _RawPeer, version: dict[str, str]) -> None:
    answers = await raw_peer.answers_to(
        _raw_frame(json.dumps({**version, "id": 1, "method": "echo", "params": {}}))
        + _raw_frame(json.dumps({**version, "method": "changed", "params": {}}))
    )

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INVALID_REQUEST, 1), (JsonRpcErrorCode.INVALID_REQUEST, None)]
    assert raw_peer.calls == []
    assert len(raw_peer.problems) == 2


@pytest.mark.parametrize("id_value", ["7", "a b", 7, 0, -5])
async def test_request_with_a_string_or_integer_id_keeps_its_id(raw_peer: _RawPeer, id_value: str | int) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=id_value, method="echo", params={})))

    assert answers == [{"jsonrpc": "2.0", "id": id_value, "result": {}}]
    assert raw_peer.calls == [("echo", {})]
    assert raw_peer.problems == []


async def test_notification_calls_its_handler_and_sends_nothing(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(method="changed", params={"a": 1})))

    assert answers == []
    assert raw_peer.calls == [("changed", {"a": 1})]
    assert raw_peer.problems == []


# --- notifications ----------------------------------------------------------


async def test_failing_notification_handler_is_reported_and_not_answered(raw_peer: _RawPeer) -> None:
    raw_peer.peer.register_notification_handler("failing", _bad_value)

    answers = await raw_peer.answers_to(_raw_frame(_rpc(method="failing", params={})))

    assert answers == []
    assert len(raw_peer.problems) == 1
    assert "'failing'" in raw_peer.problems[0]
    assert "bad value" in raw_peer.problems[0]


async def test_error_that_a_notification_handler_raises_is_reported_and_not_answered(
    raw_peer: _RawPeer, caplog: pytest.LogCaptureFixture
) -> None:
    raw_peer.peer.register_notification_handler("failing", _gone)

    answers = await raw_peer.answers_to(_raw_frame(_rpc(method="failing", params={})))

    assert answers == []
    assert len(raw_peer.problems) == 1
    assert "'failing'" in raw_peer.problems[0]
    assert "gone" in raw_peer.problems[0]
    assert len(_errors_of_the_peer(caplog)) == 1


async def test_params_of_a_notification_that_cannot_be_converted_are_reported_and_not_answered(
    raw_peer: _RawPeer,
) -> None:
    raw_peer.peer.register_notification_handler("typed", _total)

    answers = await raw_peer.answers_to(_raw_frame(_rpc(method="typed", params={"total": "not-an-int"})))

    assert answers == []
    assert len(raw_peer.problems) == 1
    assert "'typed'" in raw_peer.problems[0]


async def test_unknown_notification_is_ignored(raw_peer: _RawPeer, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="jsonrpcpeer.peer")

    answers = await raw_peer.answers_to(_raw_frame(_rpc(method="robot/unknown_notification", params={})))

    assert answers == []
    assert raw_peer.problems == []
    assert [record.levelno for record in caplog.records if "robot/unknown_notification" in record.getMessage()] == [
        logging.DEBUG
    ]


class _NotifiedEndpoint:
    rpc_peer: JsonRpcPeer | None = None

    def __init__(self) -> None:
        self.notified: list[Any] = []

    @rpc_notification("notify")
    async def notify(self, params: Any) -> None:
        self.notified.append(params)


async def test_attached_endpoint_gets_its_notifications(raw_peer: _RawPeer) -> None:
    endpoint = _NotifiedEndpoint()
    raw_peer.peer.attach_endpoint(endpoint)

    answers = await raw_peer.answers_to(_raw_frame(_rpc(method="notify", params={"a": 1})))

    assert answers == []
    assert endpoint.notified == [{"a": 1}]
    assert endpoint.rpc_peer is raw_peer.peer


# --- responses --------------------------------------------------------------


@pytest.mark.parametrize("version", [{}, {"jsonrpc": "1.0"}], ids=["missing", "1.0"])
async def test_response_of_another_version_fails_the_waiting_request(
    raw_peer: _RawPeer, version: dict[str, str]
) -> None:
    request = await _waiting_request_of(raw_peer)

    answers = await raw_peer.answers_to(_raw_frame(json.dumps({**version, "id": "1", "result": 5})))

    with pytest.raises(JsonRpcResponseError) as exc_info:
        await asyncio.wait_for(request, 2)
    assert exc_info.value.code == JsonRpcErrorCode.INVALID_REQUEST
    assert "version" in exc_info.value.message
    assert answers == []
    assert raw_peer.problems == []


@pytest.mark.parametrize(
    "response",
    [{"id": "99", "result": 5}, {"jsonrpc": "2.0", "id": "99"}],
    ids=["no version", "neither a result nor an error"],
)
async def test_invalid_response_that_no_request_waits_for_is_reported(
    raw_peer: _RawPeer, response: dict[str, Any]
) -> None:
    answers = await raw_peer.answers_to(_raw_frame(json.dumps(response)))

    assert answers == []
    assert len(raw_peer.problems) == 1
    assert "'99'" in raw_peer.problems[0]


@pytest.mark.parametrize("id_value", [{"a": 1}, True], ids=["object", "true"])
async def test_response_with_an_id_of_another_type_is_reported_and_not_answered(
    raw_peer: _RawPeer, id_value: Any
) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=id_value, result=5)))

    assert answers == []
    assert len(raw_peer.problems) == 1


async def test_null_id_with_neither_a_result_nor_an_error_is_reported(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=None)))

    assert answers == []
    assert len(raw_peer.problems) == 1


async def test_error_response_without_an_id_is_reported(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=None, error={"code": -32700, "message": "bad"})))

    assert answers == []
    assert len(raw_peer.problems) == 1
    assert "-32700" in raw_peer.problems[0]
    assert "bad" in raw_peer.problems[0]


async def test_valid_response_that_no_request_waits_for_is_ignored(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_raw_frame(_rpc(id="99", result=5)))

    assert answers == []
    assert raw_peer.problems == []


async def test_response_to_a_request_that_was_just_cancelled_is_ignored(raw_peer: _RawPeer) -> None:
    loop = asyncio.get_running_loop()
    reports: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, context: reports.append(context))
    try:
        request = await _waiting_request_of(raw_peer)

        # The read loop starts handling the response, and the request is cancelled before that runs.
        raw_peer.reader.feed_data(_raw_frame(_rpc(id="1", result=5)))
        await asyncio.sleep(0)
        raw_peer.peer._pending_requests["1"].cancel()

        answers = await raw_peer.answers_to(b"")
        with pytest.raises(asyncio.CancelledError):
            await request

        gc.collect()
        assert reports == []
        assert answers == []
        assert raw_peer.problems == []
    finally:
        loop.set_exception_handler(None)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"result": 5, "error": None}, 5),
        ({"result": None, "error": None}, None),
        ({"error": None}, -32603),
        ({"result": None, "error": {"code": -32000, "message": "boom"}}, -32000),
    ],
    ids=["result", "null result", "no result", "error next to a null result"],
)
async def test_null_error_is_no_error(raw_peer: _RawPeer, response: dict[str, Any], expected: int | None) -> None:
    request = await _waiting_request_of(raw_peer)

    raw_peer.reader.feed_data(_raw_frame(_rpc(id="1", **response)))

    if expected is None or expected == 5:
        assert await asyncio.wait_for(request, 2) == expected
    else:
        with pytest.raises(JsonRpcResponseError) as exc_info:
            await asyncio.wait_for(request, 2)
        assert exc_info.value.code == expected


# --- the request timeout ----------------------------------------------------


async def test_request_without_a_response_in_time_fails_with_a_timeout() -> None:
    raw = await _start_raw_peer(request_timeout=0.2)

    with pytest.raises(TimeoutError):
        await raw.peer.send_request("first")

    request = asyncio.create_task(raw.peer.send_request("second"))
    await _wait_until(lambda: "2" in raw.peer._pending_requests)
    raw.reader.feed_data(_raw_frame(_rpc(id="2", result=5)))

    assert await asyncio.wait_for(request, 2) == 5
    await raw.peer.stop()


async def test_response_after_the_timeout_is_ignored() -> None:
    raw = await _start_raw_peer(request_timeout=0.01)

    with pytest.raises(TimeoutError):
        await raw.peer.send_request("late")

    answers = await raw.answers_to(_raw_frame(_rpc(id="1", result=5)))
    await raw.peer.stop()

    assert answers == []
    assert raw.problems == []


# --- sending ----------------------------------------------------------------


async def _nothing(params: Any) -> None:
    return None


async def _not_writable(params: Any) -> Any:
    return object()


async def _too_long(params: Any) -> str:
    return "x" * 500


async def test_handler_without_a_result_answers_with_a_null_result(
    raw_peer: _RawPeer, peer_pair: tuple[JsonRpcPeer, JsonRpcPeer]
) -> None:
    raw_peer.peer.register_request_handler("nothing", _nothing)

    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=8, method="nothing", params={})))

    assert answers == [{"jsonrpc": "2.0", "id": 8, "result": None}]
    assert b'"result":null' in raw_peer.writer.written[0]

    client, server = peer_pair
    server.register_request_handler("nothing", _nothing)
    assert await asyncio.wait_for(client.send_request("nothing"), 2) is None


async def test_result_that_cannot_be_written_is_answered_and_logged(
    raw_peer: _RawPeer, caplog: pytest.LogCaptureFixture
) -> None:
    raw_peer.peer.register_request_handler("call", _not_writable)

    answers = await raw_peer.answers_to(_raw_frame(_rpc(id=7, method="call", params={})))

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INTERNAL_ERROR, 7)]
    errors = _errors_of_the_peer(caplog)
    assert len(errors) == 1
    assert "object" in errors[0].getMessage()


async def test_response_above_the_size_limit_is_answered_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    raw = await _start_raw_peer(max_message_size=200)
    raw.peer.register_request_handler("call", _too_long)

    answers = await raw.answers_to(_raw_frame(_rpc(id=7, method="call", params={})))
    await raw.peer.stop()

    assert _codes_and_ids(answers) == [(JsonRpcErrorCode.INTERNAL_ERROR, 7)]
    errors = _errors_of_the_peer(caplog)
    assert len(errors) == 1
    assert "exceeds maximum" in errors[0].getMessage()


async def test_remote_side_going_away_during_a_handler_leaves_nothing_behind(
    caplog: pytest.LogCaptureFixture,
) -> None:
    loop = asyncio.get_running_loop()
    reports: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, context: reports.append(context))
    try:
        reader = asyncio.StreamReader()
        writer = _WriterLostWhileDraining()
        peer = JsonRpcPeer(reader, cast("asyncio.StreamWriter", writer))

        async def echo(params: Any) -> Any:
            return params

        peer.register_request_handler("echo", echo)
        peer.start()

        reader.feed_data(_raw_frame(_REQUEST))
        await _wait_until(lambda: bool(writer.written) and not peer._inflight)
        await peer.stop()

        gc.collect()
        assert len(writer.written) == 1
        assert reports == []
        assert _errors_of_the_peer(caplog) == []
    finally:
        loop.set_exception_handler(None)


# --- batches ----------------------------------------------------------------


def _batch(*messages: str) -> bytes:
    return _raw_frame(f"[{','.join(messages)}]")


async def test_batch_with_requests_and_notifications(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(
        _batch(
            _rpc(id=1, method="echo", params={"n": 1}),
            _rpc(method="changed", params={"n": 2}),
            _rpc(id=2, method="echo", params={"n": 3}),
        )
    )

    assert answers == [
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"n": 1}},
            {"jsonrpc": "2.0", "id": 2, "result": {"n": 3}},
        ]
    ]
    assert raw_peer.calls == [("echo", {"n": 1}), ("changed", {"n": 2}), ("echo", {"n": 3})]


async def test_batch_of_notifications_sends_nothing(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(
        _batch(_rpc(method="changed", params={"n": 1}), _rpc(method="changed", params={"n": 2}))
    )

    assert answers == []
    assert raw_peer.calls == [("changed", {"n": 1}), ("changed", {"n": 2})]


async def test_batch_with_a_failing_notification(raw_peer: _RawPeer) -> None:
    raw_peer.peer.register_notification_handler("failing", _bad_value)

    answers = await raw_peer.answers_to(_batch(_rpc(id=1, method="echo", params={}), _rpc(method="failing", params={})))

    assert answers == [[{"jsonrpc": "2.0", "id": 1, "result": {}}]]
    assert len(raw_peer.problems) == 1
    assert "'failing'" in raw_peer.problems[0]


async def test_batch_with_an_invalid_element(raw_peer: _RawPeer) -> None:
    answers = await raw_peer.answers_to(_batch("1", _rpc(id=2, method="echo", params={})))

    assert len(answers) == 1
    assert answers[0][0]["id"] is None
    assert answers[0][0]["error"]["code"] == JsonRpcErrorCode.INVALID_REQUEST
    assert answers[0][1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


async def test_batch_of_responses_gives_each_request_its_response(raw_peer: _RawPeer) -> None:
    first = asyncio.create_task(raw_peer.peer.send_request("first"))
    second = asyncio.create_task(raw_peer.peer.send_request("second"))
    await _wait_until(lambda: len(raw_peer.peer._pending_requests) == 2)

    answers = await raw_peer.answers_to(_batch(_rpc(id="2", result="b"), _rpc(id="1", result="a")))

    assert list(await asyncio.wait_for(asyncio.gather(first, second), 2)) == ["a", "b"]
    assert answers == []
    assert raw_peer.problems == []


async def test_batch_with_a_result_that_cannot_be_written(raw_peer: _RawPeer) -> None:
    raw_peer.peer.register_request_handler("call", _not_writable)

    answers = await raw_peer.answers_to(
        _batch(_rpc(id=1, method="echo", params={"a": 1}), _rpc(id=2, method="call", params={}))
    )

    assert len(answers) == 1
    assert answers[0][0] == {"jsonrpc": "2.0", "id": 1, "result": {"a": 1}}
    assert (answers[0][1]["id"], answers[0][1]["error"]["code"]) == (2, JsonRpcErrorCode.INTERNAL_ERROR)


# The examples in section 7 of the JSON-RPC 2.0 specification, with the code of an error instead of the whole error.
_E = {"jsonrpc": "2.0"}
_SPECIFICATION_EXAMPLES: list[tuple[str, str, Any]] = [
    (
        "positional",
        '{"jsonrpc": "2.0", "method": "subtract", "params": [42, 23], "id": 1}',
        {**_E, "result": 19, "id": 1},
    ),
    (
        "positional 2",
        '{"jsonrpc": "2.0", "method": "subtract", "params": [23, 42], "id": 2}',
        {**_E, "result": -19, "id": 2},
    ),
    (
        "named",
        '{"jsonrpc": "2.0", "method": "subtract", "params": {"subtrahend": 23, "minuend": 42}, "id": 3}',
        {**_E, "result": 19, "id": 3},
    ),
    (
        "named 2",
        '{"jsonrpc": "2.0", "method": "subtract", "params": {"minuend": 42, "subtrahend": 23}, "id": 4}',
        {**_E, "result": 19, "id": 4},
    ),
    ("notification", '{"jsonrpc": "2.0", "method": "update", "params": [1,2,3,4,5]}', None),
    ("notification 2", '{"jsonrpc": "2.0", "method": "foobar"}', None),
    ("no such method", '{"jsonrpc": "2.0", "method": "foobar", "id": "1"}', {**_E, "error": -32601, "id": "1"}),
    (
        "invalid JSON",
        '{"jsonrpc": "2.0", "method": "foobar, "params": "bar", "baz]',
        {**_E, "error": -32700, "id": None},
    ),
    ("invalid Request", '{"jsonrpc": "2.0", "method": 1, "params": "bar"}', {**_E, "error": -32600, "id": None}),
    (
        "batch, invalid JSON",
        '[{"jsonrpc": "2.0", "method": "sum", "params": [1,2,4], "id": "1"},{"jsonrpc": "2.0", "method"]',
        {**_E, "error": -32700, "id": None},
    ),
    ("empty array", "[]", {**_E, "error": -32600, "id": None}),
    ("invalid batch of one", "[1]", [{**_E, "error": -32600, "id": None}]),
    ("invalid batch", "[1,2,3]", [{**_E, "error": -32600, "id": None}] * 3),
    (
        "batch",
        (
            '[{"jsonrpc": "2.0", "method": "sum", "params": [1,2,4], "id": "1"},'
            '{"jsonrpc": "2.0", "method": "notify_hello", "params": [7]},'
            '{"jsonrpc": "2.0", "method": "subtract", "params": [42,23], "id": "2"},'
            '{"foo": "boo"},'
            '{"jsonrpc": "2.0", "method": "foo.get", "params": {"name": "myself"}, "id": "5"},'
            '{"jsonrpc": "2.0", "method": "get_data", "id": "9"}]'
        ),
        [
            {**_E, "result": 7, "id": "1"},
            {**_E, "result": 19, "id": "2"},
            {**_E, "error": -32600, "id": None},
            {**_E, "error": -32601, "id": "5"},
            {**_E, "result": ["hello", 5], "id": "9"},
        ],
    ),
    (
        "batch of notifications",
        (
            '[{"jsonrpc": "2.0", "method": "notify_sum", "params": [1,2,4]},'
            '{"jsonrpc": "2.0", "method": "notify_hello", "params": [7]}]'
        ),
        None,
    ),
]


def _with_error_codes(answer: Any) -> Any:
    """The answer with the code of an error instead of the error, whose message is up to the implementation."""
    if isinstance(answer, list):
        return [_with_error_codes(element) for element in answer]
    return {**answer, "error": answer["error"]["code"]} if "error" in answer else answer


@pytest.mark.parametrize(
    ("message", "expected"),
    [example[1:] for example in _SPECIFICATION_EXAMPLES],
    ids=[example[0] for example in _SPECIFICATION_EXAMPLES],
)
async def test_example_of_the_json_rpc_specification(raw_peer: _RawPeer, message: str, expected: Any) -> None:
    async def subtract(params: Any) -> int:
        if isinstance(params, list):
            return int(params[0]) - int(params[1])
        return int(params["minuend"]) - int(params["subtrahend"])

    async def add_up(params: Any) -> int:
        return sum(params)

    async def get_data(params: Any) -> list[Any]:
        return ["hello", 5]

    async def notified(params: Any) -> None:
        pass

    raw_peer.peer.register_request_handler("subtract", subtract)
    raw_peer.peer.register_request_handler("sum", add_up)
    raw_peer.peer.register_request_handler("get_data", get_data)
    for method in ("update", "foobar", "notify_sum", "notify_hello"):
        raw_peer.peer.register_notification_handler(method, notified)

    answers = await raw_peer.answers_to(_raw_frame(message))

    assert [_with_error_codes(answer) for answer in answers] == ([] if expected is None else [expected])


# --- the charset ------------------------------------------------------------


async def test_peer_with_another_encoding_names_its_charset() -> None:
    raw = await _start_raw_peer(default_encoding="latin-1")

    await raw.peer.send_notification("note", {"a": "ä"})
    await raw.peer.stop()

    head, _, body = raw.writer.written[0].partition(b"\r\n\r\n")
    assert head.split(b"\r\n")[1] == b"Content-Type: application/vscode-jsonrpc; charset=latin-1"
    assert b'"a":"\xe4"' in body


@pytest.mark.parametrize("encoding", ["utf-8", "utf8", "UTF-8"])
async def test_peer_with_utf8_sends_no_content_type(encoding: str) -> None:
    raw = await _start_raw_peer(default_encoding=encoding)

    await raw.peer.send_notification("note", {"a": "ä"})
    await raw.peer.stop()

    head, _, body = raw.writer.written[0].partition(b"\r\n\r\n")
    assert b"Content-Type" not in head
    assert "ä".encode() in body


async def test_message_without_a_charset_is_read_as_utf8() -> None:
    raw = await _start_raw_peer(default_encoding="latin-1")

    raw.reader.feed_data(_raw_frame(_rpc(method="changed", params={"a": "ä"}).replace("\\u00e4", "ä")))
    await _wait_until(lambda: bool(raw.calls))
    await raw.peer.stop()

    assert raw.calls == [("changed", {"a": "ä"})]
    assert raw.problems == []


class _WriterInto(_FakeWriter):
    """A writer that hands what it gets to the reader of the other peer."""

    def __init__(self, reader: asyncio.StreamReader) -> None:
        super().__init__()
        self._reader = reader

    def write(self, data: Any) -> None:
        self._reader.feed_data(bytes(data))


async def test_peers_with_different_encodings_understand_each_other() -> None:
    async def echo(params: Any) -> Any:
        return params

    latin_reader, utf8_reader = asyncio.StreamReader(), asyncio.StreamReader()
    latin = JsonRpcPeer(
        latin_reader, cast("asyncio.StreamWriter", _WriterInto(utf8_reader)), default_encoding="latin-1"
    )
    utf8 = JsonRpcPeer(utf8_reader, cast("asyncio.StreamWriter", _WriterInto(latin_reader)))
    for peer in (latin, utf8):
        peer.register_request_handler("echo", echo)
        peer.start()

    assert await asyncio.wait_for(latin.send_request("echo", {"a": "ä"}), 2) == {"a": "ä"}
    assert await asyncio.wait_for(utf8.send_request("echo", {"a": "ä"}), 2) == {"a": "ä"}
    await latin.stop()
    await utf8.stop()


async def test_unknown_default_encoding_fails_when_the_peer_is_created() -> None:
    with pytest.raises(LookupError):
        JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", _FakeWriter()), default_encoding="nope")
