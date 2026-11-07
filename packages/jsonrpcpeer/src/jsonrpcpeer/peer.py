import abc
import asyncio
import codecs
import contextlib
import functools
import inspect
import json
import logging
import re
import traceback
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Iterator, Optional, Type, TypeAlias, TypeVar, cast, get_type_hints

from .json_helpers import as_json, from_dict

T = TypeVar("T")
E = TypeVar("E", bound="JsonRpcEndpoint")

PROTOCOL_VERSION = "2.0"

# Digits only: int() also takes "+5", "1_000" and the digits of other scripts. The bound keeps int() from refusing it.
_VALID_LENGTH = re.compile(r"[0-9]{1,18}")


class JsonRpcErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass(slots=True)
class JsonRpcMessage:
    jsonrpc: str = field(default=PROTOCOL_VERSION, init=False, metadata={"force_json": True})


@dataclass(slots=True)
class JsonRpcRequest(JsonRpcMessage):
    method: str
    id: str | int | None
    params: dict[str, Any] | list[Any] | None = None


@dataclass(slots=True)
class JsonRpcNotification(JsonRpcMessage):
    method: str
    params: dict[str, Any] | list[Any] | None = None


@dataclass(slots=True)
class JsonResponseBase(JsonRpcMessage):
    pass


@dataclass(slots=True)
class JsonRpcResponse(JsonResponseBase):
    id: str | int | None
    # No default: a field with a default is left out when it is None, and a response must have a result.
    result: Any


@dataclass(slots=True, kw_only=True)
class JsonRpcError:
    code: int
    message: str
    data: Optional[Any] = None


@dataclass(slots=True)
class JsonRpcErrorResponse(JsonResponseBase):
    error: JsonRpcError
    id: str | int | None


def _is_usable_id(value: Any) -> bool:
    # `bool` is a subclass of `int`, and JSON-RPC asks for a string or a number.
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _charset_of(content_type: str) -> str | None:
    for part in content_type.split(";"):
        name, _, value = part.partition("=")
        if name.strip().lower() == "charset":
            return value.strip().strip('"') or None
    return None


def _error_from_dict(error_data: Any) -> JsonRpcError:
    """Build a JsonRpcError from an inbound value, tolerating malformed payloads.

    Unexpected keys are ignored; a non-dict error payload is wrapped as an
    internal error so a pending request always gets resolved instead of hanging.
    """
    if not isinstance(error_data, dict):
        return JsonRpcError(code=JsonRpcErrorCode.INTERNAL_ERROR, message=str(error_data))
    return JsonRpcError(
        code=error_data.get("code", JsonRpcErrorCode.INTERNAL_ERROR),
        message=str(error_data.get("message", "")),
        data=error_data.get("data"),
    )


async def _wait_closed(writer: asyncio.StreamWriter) -> None:
    await writer.wait_closed()


def _retrieve_exception(future: "asyncio.Future[Any]") -> None:
    # Retrieve the error, e.g. from the stdio write pipe, so asyncio does not report it as never retrieved.
    # Whoever awaits the future still gets it.
    if not future.cancelled():
        future.exception()


class JsonRpcConnectionClosedError(ConnectionError):
    """Raised for a request that cannot complete because the connection is closed."""


class JsonRpcMethodAlreadyRegisteredError(ValueError):
    """Raised when a handler for a method is already registered."""


class JsonRpcResponseError(Exception):
    """An error response: raised for a request that gets one, and by a handler to answer with one."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"RPC Error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


def _failure_of_response(message: dict[str, Any]) -> JsonRpcResponseError | None:
    """The error for a response that is invalid; ``None`` for a valid one."""
    if message.get("jsonrpc") != PROTOCOL_VERSION:
        return JsonRpcResponseError(
            JsonRpcErrorCode.INVALID_REQUEST, f"Invalid JSON-RPC version in a response: {message.get('jsonrpc')!r}"
        )
    if message.get("error") is None and "result" not in message:
        return JsonRpcResponseError(JsonRpcErrorCode.INTERNAL_ERROR, "Invalid response format")
    return None


class _InvalidParamsError(Exception):
    """Internal marker: request/notification params could not be converted to the handler's type."""


THandlerCallable: TypeAlias = Callable[["JsonRpcPeer", Any], Any] | Callable[[Any], Any]


@dataclass(slots=True)
class _HandlerEntry:
    handler: THandlerCallable
    param_type: Type[Any]
    pass_peer: bool = True


class JsonRpcPeer:
    """JSON-RPC 2.0 Peer implementation for asynchronous communication.

    This implementation uses a header-based framing protocol (similar to LSP)
    where each message must be preceded by a 'Content-Length' header.
    """

    logger = logging.getLogger(__name__)

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        context: Any = None,
        *,
        request_timeout: float | None = None,
        max_message_size: int | None = None,
        default_encoding: str = "utf-8",
        auto_close: bool = True,
        send_tracebacks: bool = False,
        on_problem: Callable[[str], None] | None = None,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.context = context

        self.request_timeout: float | None = request_timeout
        self.max_message_size: int | None = max_message_size
        self.default_encoding = default_encoding
        self.auto_close = auto_close
        self.send_tracebacks = send_tracebacks
        self.on_problem = on_problem
        # Without this field, the other side reads the content as UTF-8.
        self._content_type_field = (
            ""
            if codecs.lookup(default_encoding).name == "utf-8"
            else f"Content-Type: application/vscode-jsonrpc; charset={default_encoding}\r\n"
        )

        self._request_handlers: dict[str, _HandlerEntry] = {}
        self._notification_handlers: dict[str, _HandlerEntry] = {}

        self._pending_requests: dict[str | int, asyncio.Future[Any]] = {}
        self._id_counter = 1
        # What `remote` gave out: one object for each definition.
        self._remotes: dict[type, Any] = {}

        self.running = False
        # Set once the read loop has ended: no response can arrive after that.
        self._closed = False
        # Created on first use, so that a peer can be created without a running event loop.
        self._completion_future: asyncio.Future[bool] | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._inflight: set[asyncio.Future[Any]] = set()
        # The wait for the writer to close; it may go on after the peer has stopped.
        self._closing: asyncio.Task[None] | None = None

        # JSON serialization options
        self.indent_json = None
        self.compact_json = True

    def _serialize_json(self, obj: Any) -> str:
        """Serialize an object to JSON using the configured options."""
        return as_json(obj, self.indent_json, self.compact_json)

    def _traceback_data(self) -> str | None:
        """The traceback of the exception being handled, as `data` of an error response, if the peer sends it."""
        return traceback.format_exc() if self.send_tracebacks else None

    def _report_problem(self, problem: str, *, exc_info: bool = False) -> None:
        """Log a problem with an incoming message, and hand it to the application."""
        self.logger.error("%s", problem, exc_info=exc_info)
        if self.on_problem is not None:
            try:
                self.on_problem(problem)
            except Exception:
                self.logger.exception("The callback for problems with messages failed")

    def _completion(self) -> asyncio.Future[bool]:
        """The completion future, bound to the event loop that is running when it is first used."""
        if self._completion_future is None:
            self._completion_future = asyncio.get_running_loop().create_future()
            # Nobody has to wait for it, for example after a session failed to start.
            self._completion_future.add_done_callback(_retrieve_exception)
        return self._completion_future

    @property
    def completion(self) -> asyncio.Future[bool]:
        return self._completion()

    def start(self) -> None:
        self.running = True
        self._read_task = asyncio.create_task(self.io_loop())

    async def stop(self) -> None:
        self.running = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        await self._cancel_inflight()
        if not self._closed:
            # The read loop never ran its cleanup: the peer was never started, or its read
            # task was cancelled before its first step. As after a cancelled cleanup, the
            # writer goes on closing without stop() waiting for it.
            await self._finish(None, wait_for_close=False)
        await self.completion

    async def _cancel_inflight(self) -> None:
        tasks = list(self._inflight)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self) -> None:
        self.start()
        await self.completion

    def _get_and_check_handler_param_type(
        self,
        handler: THandlerCallable,
    ) -> tuple[Type[Any], bool]:
        sig = inspect.signature(handler)
        params = list(sig.parameters.values())
        type_hints = get_type_hints(handler)

        if len(params) == 2:
            first_param_type = type_hints.get(params[0].name)
            if first_param_type is not JsonRpcPeer:
                raise ValueError("First parameter of handler must be of type JsonRpcPeer")

            return cast(Type[Any], type_hints.get(params[1].name, Any)), True

        if len(params) == 1:
            return cast(Type[Any], type_hints.get(params[0].name, Any)), False

        raise ValueError("Handler must have signature (peer: JsonRpcPeer, params: T) -> R or (params: T) -> R")

    def register_request_handler(
        self,
        method_name: str,
        handler: THandlerCallable,
    ) -> None:
        if not method_name or method_name.isspace():
            raise ValueError("Method name cannot be null or whitespace")

        if method_name in self._request_handlers:
            raise JsonRpcMethodAlreadyRegisteredError(f"Request handler for method '{method_name}' already exists")

        param_type, pass_peer = self._get_and_check_handler_param_type(handler)

        self._request_handlers[method_name] = _HandlerEntry(handler=handler, param_type=param_type, pass_peer=pass_peer)

    def register_notification_handler(
        self,
        method_name: str,
        handler: THandlerCallable,
    ) -> None:
        if not method_name or method_name.isspace():
            raise ValueError("Method name cannot be null or whitespace")

        if method_name in self._notification_handlers:
            raise JsonRpcMethodAlreadyRegisteredError(f"Notification handler for method '{method_name}' already exists")

        param_type, pass_peer = self._get_and_check_handler_param_type(handler)

        self._notification_handlers[method_name] = _HandlerEntry(
            handler=handler, param_type=param_type, pass_peer=pass_peer
        )

    def _encode_message(self, message: Any) -> bytes:
        """The content of a frame for ``message``. Raises if it cannot be written or is too long."""
        body_bytes = (self._serialize_json(message) + "\r\n").encode(self.default_encoding)

        if self.max_message_size is not None and len(body_bytes) > self.max_message_size:
            raise ValueError(f"Outgoing message size {len(body_bytes)} exceeds maximum {self.max_message_size}")

        return body_bytes

    def _write_frame(self, body_bytes: bytes) -> None:
        header = f"Content-Length: {len(body_bytes)}\r\n{self._content_type_field}\r\n"
        self.writer.write(memoryview(header.encode("ascii") + body_bytes))

    async def _send_message(self, message: Any) -> None:
        self._write_frame(self._encode_message(message))

        await self.writer.drain()

    def _encode_response(self, response: "JsonRpcResponse | JsonRpcErrorResponse") -> bytes:
        """The content of a frame for ``response``, or for an error to the same request if it cannot be sent."""
        try:
            return self._encode_message(response)
        except Exception as ex:
            self.logger.exception("The response to request %r cannot be sent: %s", response.id, ex)
            error = JsonRpcErrorResponse(
                id=response.id,
                error=JsonRpcError(code=JsonRpcErrorCode.INTERNAL_ERROR, message=str(ex), data=self._traceback_data()),
            )
            # Without the size check, and with every character writable: this answer must get through.
            return (self._serialize_json(error) + "\r\n").encode(self.default_encoding, "backslashreplace")

    async def _write_answer(self, body_bytes: bytes) -> None:
        """Send an answer. If that fails, the other side is gone, and nobody is left to tell."""
        try:
            self._write_frame(body_bytes)
            await self.writer.drain()
        except Exception as ex:
            self.logger.debug("Could not send an answer: %s", ex)

    async def _answer_problem(self, code: JsonRpcErrorCode, problem: str, data: Any = None) -> None:
        """Report a message that cannot be read, and answer it with an error without an id."""
        self._report_problem(problem)
        await self._write_answer(
            self._encode_response(
                JsonRpcErrorResponse(id=None, error=JsonRpcError(code=code, message=problem, data=data))
            )
        )

    async def send_notification(self, method: str, params: Optional[Any] = None) -> None:
        if self._closed:
            raise JsonRpcConnectionClosedError(f"Cannot send notification '{method}': the connection is closed")

        message = JsonRpcNotification(method=method)
        if params is not None:
            message.params = params

        await self._send_message(message)

    async def send_request(self, method: str, params: Optional[Any] = None) -> Any:
        return await self.send_request_typed(None, method, params)

    async def send_request_typed(
        self,
        response_type: Type[T] | None,
        method: str,
        params: Optional[Any] = None,
    ) -> T:
        if self._closed:
            raise JsonRpcConnectionClosedError(f"Cannot send request '{method}': the connection is closed")

        tcs: asyncio.Future[Any] = asyncio.Future()

        id_str = str(self._id_counter)
        self._id_counter += 1
        self._pending_requests[id_str] = tcs

        message = JsonRpcRequest(method=method, id=id_str)
        message.jsonrpc = PROTOCOL_VERSION
        if params is not None:
            message.params = params
        else:
            message.params = {}

        try:
            try:
                await self._send_message(message)
            except Exception:
                # If the connection closed while the request was being written, the closure has
                # already failed it: report that instead of the write error. Reading the exception
                # also keeps asyncio from logging it as never retrieved.
                closed_error = tcs.exception() if tcs.done() and not tcs.cancelled() else None
                if isinstance(closed_error, JsonRpcConnectionClosedError):
                    raise closed_error
                raise

            if self.request_timeout is not None:
                response = await asyncio.wait_for(tcs, timeout=self.request_timeout)
            else:
                response = await tcs

            if response_type is None:
                return cast(T, response.result)

            return from_dict(response.result, response_type)
        finally:
            self._pending_requests.pop(id_str, None)

    async def io_loop(self) -> None:
        # The error that ended the loop, if any; it becomes the cause of the failed requests.
        close_error: BaseException | None = None
        try:
            while self.running:
                await self._read_message()
        except asyncio.IncompleteReadError as e:
            if e.partial or not self.reader.at_eof():
                close_error = e
                if not self._completion().done():
                    self._completion().set_exception(e)
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            close_error = e
            if not self._completion().done():
                self._completion().set_exception(e)
        finally:
            await self._finish(close_error)

    async def _read_header_line(self) -> str | None:
        """Read a line of a header part, without its line end; ``None`` if it is too long to be a known header."""
        too_long = False
        while True:
            try:
                line_bytes = await self.reader.readuntil(b"\r\n")
            except asyncio.LimitOverrunError as ex:
                # The reader keeps the bytes in its buffer. Drop them, and the rest of the line with the next read.
                await self.reader.readexactly(ex.consumed)
                too_long = True
            else:
                return None if too_long else line_bytes[:-2].decode("ascii", "replace")

    async def _read_header_part(self) -> tuple[str | None, str | None]:
        """Read a header part. Returns the values of Content-Length and of the charset, if it has them."""
        length = None
        charset = None
        while True:
            line = await self._read_header_line()
            if line == "":
                return length, charset
            if line is None:
                continue
            name, _, value = line.partition(":")
            name = name.strip().lower()
            if name == "content-length":
                length = value.strip()
            elif name == "content-type":
                charset = _charset_of(value)

    def _start_task(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)

    async def _skip_content(self, length: int) -> None:
        """Drop the next ``length`` bytes, in pieces, so that they do not pile up in memory."""
        while length > 0:
            chunk = await self.reader.read(min(length, 65536))
            if not chunk:
                return
            length -= len(chunk)

    async def _read_message(self) -> None:
        """Read one message and start handling it. If it cannot be read, report that and go on with the next one."""
        raw_length, charset = await self._read_header_part()

        if raw_length is None:
            self._report_problem("Received a header part without a Content-Length header")
            return
        if _VALID_LENGTH.fullmatch(raw_length) is None:
            self._report_problem(f"Received an invalid Content-Length header: {raw_length[:100]!r}")
            return

        length = int(raw_length)
        if self.max_message_size is not None and length > self.max_message_size:
            problem = f"Message size {length} exceeds maximum {self.max_message_size}"
            self._start_task(self._answer_problem(JsonRpcErrorCode.INVALID_REQUEST, problem))
            await self._skip_content(length)
            return

        body_bytes = await self.reader.readexactly(length)

        encoding = charset or "utf-8"
        try:
            message = body_bytes.decode(encoding)
        except (LookupError, ValueError) as ex:
            problem = f"Cannot decode a message with the charset {encoding!r}: {ex}"
            self._start_task(self._answer_problem(JsonRpcErrorCode.PARSE_ERROR, problem, self._traceback_data()))
            return

        self._start_task(self.handle_message(message))

    async def _finish(self, close_error: BaseException | None, *, wait_for_close: bool = True) -> None:
        """End the peer: fail the waiting requests, resolve the completion and, with auto_close, close the writer."""
        self.running = False
        # Before anything awaits, so no request can be registered in between.
        self._mark_closed(close_error)

        if not self._completion().done():
            self._completion().set_result(True)

        if self.auto_close:
            self.writer.close()
            # All callers of wait_closed() share one close future. Wait for it shielded, so that
            # stop() cancelling this wait does not cancel the close for the other callers.
            self._closing = asyncio.ensure_future(_wait_closed(self.writer))
            self._closing.add_done_callback(_retrieve_exception)
            if wait_for_close:
                # Some writers raise from wait_closed(); the completion future is
                # already set, so ignore cleanup errors here.
                with contextlib.suppress(Exception):
                    await asyncio.shield(self._closing)

    def _mark_closed(self, cause: BaseException | None) -> None:
        """Mark the connection closed and fail every request still waiting for a response."""
        self._closed = True
        pending = list(self._pending_requests.values())
        self._pending_requests.clear()
        for tcs in pending:
            if not tcs.done():
                error = JsonRpcConnectionClosedError("Connection closed before a response was received")
                error.__cause__ = cause
                tcs.set_exception(error)

    async def handle_message(self, json_str: str) -> None:
        try:
            json_element = json.loads(json_str)
        except (ValueError, RecursionError) as ex:
            # A huge integer and deep nesting do not raise JSONDecodeError.
            await self._answer_problem(JsonRpcErrorCode.PARSE_ERROR, f"Parse error: {ex}", self._traceback_data())
            return

        if isinstance(json_element, list):
            await self._handle_batch(json_element)
            return

        response = await self.process_single_message(json_element)
        if response is not None:
            await self._write_answer(self._encode_response(response))

    async def _handle_batch(self, elements: list[Any]) -> None:
        if not elements:
            await self._answer_problem(JsonRpcErrorCode.INVALID_REQUEST, "Invalid Request: batch must not be empty")
            return

        responses = []
        for element in elements:
            response = await self.process_single_message(element)
            if response is not None:
                responses.append(response)

        if responses:
            # Each response on its own, so that one that cannot be sent does not take the others with it.
            items = [self._encode_response(response).decode(self.default_encoding).rstrip() for response in responses]
            await self._write_answer(f"[{','.join(items)}]\r\n".encode(self.default_encoding))

    def _invalid_message(self, problem: str, id_value: str | int | None) -> JsonRpcErrorResponse:
        self._report_problem(problem)
        return JsonRpcErrorResponse(
            id=id_value, error=JsonRpcError(code=JsonRpcErrorCode.INVALID_REQUEST, message=problem)
        )

    async def process_single_message(self, json_element: Any) -> JsonRpcResponse | JsonRpcErrorResponse | None:
        """Handle one message. Returns the answer to it, if it gets one."""
        if not isinstance(json_element, dict):
            return self._invalid_message("Invalid JSON-RPC payload", None)

        id_value = json_element.get("id")
        if "id" in json_element and "method" not in json_element:
            self._handle_response(json_element, id_value)
            return None

        usable_id = id_value if _is_usable_id(id_value) else None

        if json_element.get("jsonrpc") != PROTOCOL_VERSION:
            return self._invalid_message("Invalid JSON-RPC version", usable_id)

        method = json_element.get("method")
        if not isinstance(method, str):
            return self._invalid_message("Invalid Request: a message needs a string as its method", usable_id)

        params = json_element.get("params")
        # A null counts as missing: some serializers write every field.
        if params is not None and not isinstance(params, (dict, list)):
            return self._invalid_message("Invalid Request: the params must be an array or an object", usable_id)

        if "id" not in json_element:
            await self.process_notification(JsonRpcNotification(method=method, params=params))
            return None

        if usable_id is None:
            return self._invalid_message("Invalid Request: the id must be a string or an integer", None)

        return await self.process_request(JsonRpcRequest(method=method, id=usable_id, params=params))

    def _handle_response(self, message: dict[str, Any], id_value: Any) -> None:
        """Hand a response to the request that waits for it. A response is never answered."""
        if id_value is None:
            error = _error_from_dict(message["error"]) if message.get("error") is not None else None
            if error is None:
                self._report_problem("Received a response without an id and without an error")
            else:
                details = "" if error.data is None else f" ({error.data})"
                self._report_problem(f"Received an error without an id: {error.code}: {error.message}{details}")
            return

        if not _is_usable_id(id_value):
            self._report_problem(f"Received a response with an invalid id: {id_value!r}")
            return

        waiting = self._pending_requests.pop(id_value, None)
        if waiting is not None and waiting.done():
            # It has just timed out or been cancelled, and its caller has not run yet.
            waiting = None

        failure = _failure_of_response(message)
        if waiting is None:
            # A valid response that nobody waits for is normal after a timeout.
            if failure is not None:
                self._report_problem(f"Received an invalid response to request {id_value!r}: {failure.message}")
        elif failure is not None:
            waiting.set_exception(failure)
        elif message.get("error") is not None:
            error = _error_from_dict(message["error"])
            waiting.set_exception(JsonRpcResponseError(error.code, error.message, error.data))
        else:
            waiting.set_result(JsonRpcResponse(id=id_value, result=message["result"]))

    async def _call_handler(
        self,
        handler: _HandlerEntry,
        params: Any,
    ) -> Any:
        try:
            converted = from_dict(params, handler.param_type)
        except Exception as ex:
            raise _InvalidParamsError(str(ex)) from ex

        if handler.pass_peer:
            result = cast(Callable[["JsonRpcPeer", Any], Any], handler.handler)(self, converted)
        else:
            result = cast(Callable[[Any], Any], handler.handler)(converted)

        # A plain function has its result already; one that returns an awaitable counts as async.
        return await result if inspect.isawaitable(result) else result

    async def process_request(self, message: JsonRpcRequest) -> JsonRpcResponse | JsonRpcErrorResponse:
        if message.method in self._request_handlers:
            handler = self._request_handlers[message.method]
            try:
                result = await self._call_handler(handler, message.params)
                return JsonRpcResponse(id=message.id, result=result)
            except JsonRpcResponseError as ex:
                return JsonRpcErrorResponse(
                    id=message.id,
                    error=JsonRpcError(code=ex.code, message=ex.message, data=ex.data),
                )
            except _InvalidParamsError as ex:
                return JsonRpcErrorResponse(
                    id=message.id,
                    error=JsonRpcError(
                        code=JsonRpcErrorCode.INVALID_PARAMS,
                        message=str(ex),
                        data=self._traceback_data(),
                    ),
                )
            except Exception as ex:
                self.logger.exception("The handler of request '%s' failed", message.method)
                return JsonRpcErrorResponse(
                    id=message.id,
                    error=JsonRpcError(
                        code=JsonRpcErrorCode.INTERNAL_ERROR,
                        message=str(ex),
                        data=self._traceback_data(),
                    ),
                )
        else:
            return JsonRpcErrorResponse(
                id=message.id,
                error=JsonRpcError(
                    code=JsonRpcErrorCode.METHOD_NOT_FOUND,
                    message=f"Method for request `{message.method}` not found",
                ),
            )

    async def process_notification(self, message: JsonRpcNotification) -> None:
        handler = self._notification_handlers.get(message.method)
        if handler is None:
            self.logger.debug("No handler for notification '%s'", message.method)
            return

        try:
            await self._call_handler(handler, message.params)
        except _InvalidParamsError as ex:
            self._report_problem(f"The params of notification '{message.method}' are invalid: {ex}")
        except JsonRpcResponseError as ex:
            self._report_problem(f"The handler of notification '{message.method}' failed: {ex.message}")
        except Exception as ex:
            self._report_problem(f"The handler of notification '{message.method}' failed: {ex}", exc_info=True)

    def attach_endpoint(self, endpoint: "JsonRpcEndpoint") -> None:
        endpoint.rpc_peer = self
        for name, request_method, notification_method in _rpc_members(type(endpoint)):
            if request_method is not None:
                self.register_request_handler(request_method, getattr(endpoint, name))
            if notification_method is not None:
                self.register_notification_handler(notification_method, getattr(endpoint, name))

    # A `Callable`, because mypy refuses an abstract class where a `type[E]` is expected.
    def remote(self, definition: Callable[..., E]) -> E:
        """The other side of this connection, as ``definition`` states it: calling a marked method sends it."""
        if not (isinstance(definition, type) and issubclass(definition, JsonRpcEndpoint)):
            raise TypeError(f"{definition!r} is not a subclass of JsonRpcEndpoint")

        known = self._remotes.get(definition)
        if known is not None:
            return cast(E, known)

        remote: E = object.__new__(_remote_class(definition))
        remote.rpc_peer = self
        self._remotes[definition] = remote
        return remote


def _rpc_members(owner: Type[Any]) -> Iterator[tuple[str, str | None, str | None]]:
    """The marked methods of a class: the attribute, and the name of the request or the notification.

    An override has no mark of its own and implements the method of its definition, so the mark comes
    from the nearest class that has one. A mark that a class does not override belongs to another
    definition of that name, and counts too. Reading the classes runs no property of an endpoint.
    """
    for name in dir(owner):
        marked: list[Type[Any]] = []
        for cls in owner.__mro__:
            member = vars(cls).get(name)
            # A staticmethod or a classmethod holds the marked function.
            function = getattr(member, "__func__", member)
            request_method = getattr(function, "rpc_request_method", None)
            notification_method = getattr(function, "rpc_notification_method", None)
            if request_method is None and notification_method is None:
                continue
            if not any(issubclass(nearer, cls) for nearer in marked):
                marked.append(cls)
                yield name, request_method, notification_method


def _remote_method(
    definition: Type[Any], name: str, request_method: str | None, notification_method: str | None
) -> Callable[..., Any]:
    """What a marked method does on the object from ``remote``: it sends."""
    method = getattr(definition, name)
    signature = inspect.signature(method)
    if len(signature.parameters) != 2:
        raise TypeError(f"{definition.__name__}.{name} must take one parameter besides self, the params")
    if not inspect.iscoroutinefunction(method):
        raise TypeError(f"{definition.__name__}.{name} must be async: a call over the connection always waits")
    parameter = list(signature.parameters)[1]
    result_type = get_type_hints(method).get("return")

    async def send(self: "JsonRpcEndpoint", *args: Any, **kwargs: Any) -> Any:
        # As the definition states it: a type checker accepts the params as a keyword.
        arguments = signature.bind(self, *args, **kwargs)
        arguments.apply_defaults()
        params = arguments.arguments[parameter]
        peer = cast(JsonRpcPeer, self.rpc_peer)
        if request_method is not None:
            return await peer.send_request_typed(result_type, request_method, params)
        await peer.send_notification(cast(str, notification_method), params)
        return None

    return send


@functools.cache
def _remote_class(definition: Type[Any]) -> Type[Any]:
    """A subclass of ``definition`` whose marked methods send. Built once for each definition."""
    members: dict[str, Any] = {"__module__": definition.__module__}
    for name, request_method, notification_method in _rpc_members(definition):
        # With several marks for a name, the nearest decides.
        if name not in members:
            members[name] = _remote_method(definition, name, request_method, notification_method)
    return type(f"Remote{definition.__name__}", (definition,), members)


class JsonRpcEndpoint(abc.ABC):
    """An interface of RPC methods. One side of a connection implements it, the other side calls it.

    A definition is a subclass whose methods carry ``rpc_request`` or ``rpc_notification``, and usually
    ``abstractmethod``. Each takes one parameter, the params. A subclass of the definition implements it,
    and ``JsonRpcPeer.attach_endpoint`` registers its methods. ``JsonRpcPeer.remote`` calls it.
    """

    rpc_peer: JsonRpcPeer | None = None

    def remote(self, definition: Callable[..., E]) -> E:
        """The other side of the peer that this endpoint is attached to."""
        if self.rpc_peer is None:
            raise RuntimeError(f"{type(self).__name__} is not attached to a peer")
        return self.rpc_peer.remote(definition)


F = TypeVar("F", bound=THandlerCallable | Callable[..., Any])


def rpc_request(method_name: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        setattr(func, "rpc_request_method", method_name)
        return func

    return decorator


def rpc_notification(method_name: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        setattr(func, "rpc_notification_method", method_name)
        return func

    return decorator
