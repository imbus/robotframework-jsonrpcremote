import asyncio
import contextlib
import inspect
import json
import logging
import traceback
import weakref
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Optional, Protocol, Type, TypeAlias, TypeVar, cast, get_type_hints

from .json_helpers import as_json, from_dict

T = TypeVar("T")

PROTOCOL_VERSION = "2.0"


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
    result: Any = None


@dataclass(slots=True, kw_only=True)
class JsonRpcError:
    code: int
    message: str
    data: Optional[Any] = None


@dataclass(slots=True)
class JsonRpcErrorResponse(JsonResponseBase):
    error: JsonRpcError
    id: str | int | None


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


class JsonRpcInvalidRequestError(Exception):
    error_code = JsonRpcErrorCode.INVALID_REQUEST


class JsonRpcMethodAlreadyRegisteredError(ValueError):
    """Raised when a handler for a method is already registered."""


class _InvalidParamsError(Exception):
    """Internal marker: request/notification params could not be converted to the handler's type."""


THandlerCallable: TypeAlias = (
    Callable[["JsonRpcPeer", Any], Coroutine[Any, Any, Any]] | Callable[[Any], Coroutine[Any, Any, Any]]
)


@dataclass(slots=True)
class _HandlerEntry:
    handler: THandlerCallable
    param_type: Type[Any]
    pass_peer: bool = True


class JsonRpcEndpointProtocol(Protocol):
    rpc_peer: "JsonRpcPeer | None"


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
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.context = context

        self.request_timeout: float | None = request_timeout
        self.max_message_size: int | None = max_message_size
        self.default_encoding = default_encoding
        self.auto_close = auto_close

        self._request_handlers: dict[str, _HandlerEntry] = {}
        self._notification_handlers: dict[str, _HandlerEntry] = {}

        self._pending_requests: dict[str | int, asyncio.Future[Any]] = {}
        self._id_counter = 1

        self.running = False
        self._completion_future: asyncio.Future[bool] = asyncio.Future()
        self._read_task: asyncio.Task[None] | None = None
        self._inflight: set[asyncio.Future[Any]] = set()

        # JSON serialization options
        self.indent_json = None
        self.compact_json = True

        weakref.finalize(self, self._on_finalize)

    def _serialize_json(self, obj: Any) -> str:
        """Serialize an object to JSON using the configured options."""
        return as_json(obj, self.indent_json, self.compact_json)

    def _on_finalize(self) -> None:
        if not self.running:
            return

        self.running = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()

    @property
    def completion(self) -> asyncio.Future[bool]:
        return self._completion_future

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

    async def _send_message(self, message: Any) -> None:
        json_str = self._serialize_json(message)
        body_bytes = (json_str + "\r\n").encode(self.default_encoding)

        if self.max_message_size is not None and len(body_bytes) > self.max_message_size:
            raise ValueError(f"Outgoing message size {len(body_bytes)} exceeds maximum {self.max_message_size}")

        header = f"Content-Length: {len(body_bytes)}\r\n\r\n"
        header_bytes = header.encode("ascii")

        self.writer.write(memoryview(header_bytes + body_bytes))

        await self.writer.drain()

    async def send_notification(self, method: str, params: Optional[Any] = None) -> None:
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
            await self._send_message(message)

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
        try:
            while self.running:
                content_length = 0
                encoding = self.default_encoding

                # Read headers
                while True:
                    line_bytes = await self.reader.readuntil(b"\r\n")
                    line = line_bytes.decode("ascii").strip()

                    if not line:
                        break

                    if line.startswith("Content-Length: "):
                        content_length = int(line[16:])

                        if self.max_message_size is not None and content_length > self.max_message_size:
                            self.logger.warning(
                                "Message size %d exceeds maximum %d, closing connection",
                                content_length,
                                self.max_message_size,
                            )
                            self.running = False
                            return

                    elif line.startswith("Content-Type: "):
                        content_type = line[14:]
                        parts = content_type.split(";")
                        for part in parts:
                            part = part.strip()
                            if part.startswith("charset="):
                                charset = part[8:].strip().strip('"')
                                if charset:
                                    encoding = charset

                # Read body
                body_bytes = await self.reader.readexactly(content_length)

                message = body_bytes.decode(encoding)
                task = asyncio.create_task(self.handle_message(message))
                self._inflight.add(task)
                task.add_done_callback(self._inflight.discard)

        except asyncio.IncompleteReadError as e:
            if e.partial or not self.reader.at_eof():
                if not self._completion_future.done():
                    self._completion_future.set_exception(e)
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            if not self._completion_future.done():
                self._completion_future.set_exception(e)
        finally:
            self.running = False

            if not self._completion_future.done():
                self._completion_future.set_result(True)

            if self.auto_close:
                self.writer.close()
                # Best-effort: completion is already signalled, so don't let cleanup
                # errors surface as unretrieved task exceptions. Some writers (e.g. the
                # asyncio stdout write pipe used by the stdio transport) raise
                # NotImplementedError from wait_closed(); others may report a reset.
                with contextlib.suppress(Exception):
                    await self.writer.wait_closed()

    async def handle_message(self, json_str: str) -> None:
        response_id: str | int | None = None
        try:
            json_element = json.loads(json_str)

            if isinstance(json_element, list):
                if not json_element:
                    await self._send_message(
                        JsonRpcErrorResponse(
                            id=None,
                            error=JsonRpcError(
                                code=JsonRpcErrorCode.INVALID_REQUEST,
                                message="Invalid Request: batch must not be empty",
                            ),
                        )
                    )
                    return

                responses = []

                for element in json_element:
                    response = await self.process_single_message(element)
                    if response is not None:
                        responses.append(response)

                if responses:
                    await self._send_message(responses)
            else:
                response = await self.process_single_message(json_element)
                if response is not None:
                    if isinstance(response, JsonRpcResponse):
                        response_id = response.id
                    await self._send_message(response)

        except json.JSONDecodeError as ex:
            error_response = JsonRpcErrorResponse(
                error=JsonRpcError(
                    code=JsonRpcErrorCode.PARSE_ERROR,
                    message=str(ex),
                    data=traceback.format_exc(),
                ),
                id=response_id,
            )
            await self._send_message(error_response)
        except JsonRpcInvalidRequestError as ex:
            error_response = JsonRpcErrorResponse(
                error=JsonRpcError(
                    code=JsonRpcInvalidRequestError.error_code,
                    message=str(ex),
                    data=traceback.format_exc(),
                ),
                id=response_id,
            )
            await self._send_message(error_response)
        except Exception as ex:
            error_response = JsonRpcErrorResponse(
                error=JsonRpcError(
                    code=JsonRpcErrorCode.INTERNAL_ERROR,
                    message=str(ex),
                    data=traceback.format_exc(),
                ),
                id=response_id,
            )
            await self._send_message(error_response)

    async def process_single_message(self, json_element: Any) -> Optional[JsonResponseBase]:
        if not isinstance(json_element, dict):
            return JsonRpcErrorResponse(
                id=None,
                error=JsonRpcError(
                    code=JsonRpcErrorCode.INVALID_REQUEST,
                    message="Invalid JSON-RPC payload",
                ),
            )

        json_rpc_version = json_element.pop("jsonrpc", None)
        if json_rpc_version != PROTOCOL_VERSION:
            return JsonRpcErrorResponse(
                id=json_element.get("id", None),
                error=JsonRpcError(
                    code=JsonRpcErrorCode.INVALID_REQUEST,
                    message="Invalid JSON-RPC version",
                ),
            )

        match json_element:
            case {"id": id_value} if "method" not in json_element:
                return await self._handle_response(json_element, id_value)

            case {"id": id_value, "method": method_name} if id_value is not None:
                request = JsonRpcRequest(method=method_name, id=id_value, params=json_element.get("params"))
                return await self.process_request(request)

            case {"method": method_name}:
                notification = JsonRpcNotification(method=method_name, params=json_element.get("params"))
                return await self.process_notification(notification)

            case _:
                return None

    async def _handle_response(self, json_element: dict[str, Any], id_value: Any) -> Optional[JsonResponseBase]:
        """Handle JSON-RPC response messages using pattern matching."""
        if id_value is not None and not isinstance(id_value, (str, int)):
            return JsonRpcErrorResponse(
                id=None,
                error=JsonRpcError(
                    code=JsonRpcErrorCode.INVALID_REQUEST,
                    message="Invalid ID type in response",
                ),
            )

        tcs = None
        if id_value is not None:
            tcs = self._pending_requests.pop(id_value, None)

        if tcs is not None:
            match json_element:
                case {"error": error_data}:
                    error = _error_from_dict(error_data)
                    tcs.set_exception(
                        Exception(
                            f"RPC Error {error.code}: {error.message}" + (f" ({error.data})" if error.data else "")
                        )
                    )
                case {"result": result}:
                    response = JsonRpcResponse(
                        id=cast(str | int, id_value),
                        result=result,
                    )
                    tcs.set_result(response)
                case _:
                    tcs.set_exception(Exception("RPC Error: Invalid response format"))
            return None

        # Handle error with null ID
        if id_value is None and "error" in json_element:
            error = _error_from_dict(json_element["error"])
            self.logger.warning(
                "Received error with null ID: %s: %s (%s)",
                error.code,
                error.message,
                error.data,
            )

        return None

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
            handler_with_peer = cast(Callable[["JsonRpcPeer", Any], Coroutine[Any, Any, Any]], handler.handler)
            return await handler_with_peer(self, converted)

        return await cast(Callable[[Any], Coroutine[Any, Any, Any]], handler.handler)(converted)

    async def process_request(self, message: JsonRpcRequest) -> JsonResponseBase:
        if message.method in self._request_handlers:
            handler = self._request_handlers[message.method]
            try:
                result = await self._call_handler(handler, message.params)
                return JsonRpcResponse(id=message.id, result=result)
            except _InvalidParamsError as ex:
                return JsonRpcErrorResponse(
                    id=message.id,
                    error=JsonRpcError(
                        code=JsonRpcErrorCode.INVALID_PARAMS,
                        message=str(ex),
                        data=traceback.format_exc(),
                    ),
                )
            except Exception as ex:
                return JsonRpcErrorResponse(
                    id=message.id,
                    error=JsonRpcError(
                        code=JsonRpcErrorCode.INTERNAL_ERROR,
                        message=str(ex),
                        data=traceback.format_exc(),
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

    async def process_notification(self, message: JsonRpcNotification) -> Optional[JsonResponseBase]:
        if message.method in self._notification_handlers:
            handler = self._notification_handlers[message.method]
            try:
                await self._call_handler(handler, message.params)
                return None
            except _InvalidParamsError as ex:
                return JsonRpcErrorResponse(
                    id=None,
                    error=JsonRpcError(
                        code=JsonRpcErrorCode.INVALID_PARAMS,
                        message=str(ex),
                        data=traceback.format_exc(),
                    ),
                )
            except Exception as ex:
                return JsonRpcErrorResponse(
                    id=None,
                    error=JsonRpcError(
                        code=JsonRpcErrorCode.INTERNAL_ERROR,
                        message=str(ex),
                        data=traceback.format_exc(),
                    ),
                )
        else:
            return JsonRpcErrorResponse(
                id=None,
                error=JsonRpcError(
                    code=JsonRpcErrorCode.METHOD_NOT_FOUND,
                    message=f"Method for notification `{message.method}` not found",
                ),
            )

    def attach_endpoint(self, endpoint: JsonRpcEndpointProtocol) -> None:
        endpoint.rpc_peer = self
        for name in dir(endpoint):
            attr = getattr(endpoint, name)
            if hasattr(attr, "rpc_request_method"):
                self.register_request_handler(attr.rpc_request_method, attr)
            if hasattr(attr, "rpc_notification_method"):
                self.register_notification_handler(attr.rpc_notification_method, attr)


class JsonRpcEndpoint:
    def __init__(self) -> None:
        self._request_handlers: dict[str, Any] = {}
        self._notification_handlers: dict[str, Any] = {}

    def request(self, method: str) -> Any:
        def decorator(func: Any) -> Any:
            self._request_handlers[method] = func
            return func

        return decorator

    def notification(self, method: str) -> Any:
        def decorator(func: Any) -> Any:
            self._notification_handlers[method] = func
            return func

        return decorator

    def register(self, peer: JsonRpcPeer) -> None:
        for method, handler in self._request_handlers.items():
            peer.register_request_handler(method, handler)
        for method, handler in self._notification_handlers.items():
            peer.register_notification_handler(method, handler)


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
