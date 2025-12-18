import asyncio
import json
import logging
import traceback
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Optional, Type, TypeVar, cast, get_type_hints

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


class JsonRpcInvalidRequestError(Exception):
    error_code = JsonRpcErrorCode.INVALID_REQUEST


@dataclass
class _HanderEntry:
    handler: Callable[["JsonRpcPeer", Any], Coroutine[Any, Any, Any]]
    param_type: Type[Any]


class JsonRpcPeer:
    """JSON-RPC 2.0 Peer implementation for asynchronous communication."""

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
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.context = context

        self.request_timeout: float | None = request_timeout
        self.max_message_size: int | None = max_message_size
        self.default_encoding = default_encoding

        self._request_handlers: dict[str, _HanderEntry] = {}
        self._notification_handlers: dict[str, _HanderEntry] = {}

        self._pending_requests: dict[str | int, asyncio.Future[Any]] = {}
        self._id_counter = 1
        self._id_lock = asyncio.Lock()

        self.running = False
        self._completion_future: asyncio.Future[bool] = asyncio.Future()
        self._read_task: asyncio.Task[None] | None = None

        # JSON serialization options
        self.indent_json = None
        self.compact_json = True

    def _serialize_json(self, obj: Any) -> str:
        """Serialize an object to JSON using the configured options."""
        return as_json(obj, self.indent_json, self.compact_json)

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
        await self.completion

    async def run(self) -> None:
        self.start()
        await self.completion

    def _get_and_check_handler_param_type(
        self,
        handler: Callable[["JsonRpcPeer", Any], Coroutine[Any, Any, Any]],
    ) -> Type[Any]:
        type_hints = list(get_type_hints(handler).values())
        if len(type_hints) != 3:
            raise ValueError("Handler must have exactly two parameters: peer and params and needs type hints")

        if type_hints[0] is not JsonRpcPeer:
            raise ValueError("First parameter of handler must be of type JsonRpcPeer")

        return cast(Type[Any], type_hints[1])

    def register_request_handler(
        self,
        method_name: str,
        handler: Callable[["JsonRpcPeer", Any], Coroutine[Any, Any, Any]],
    ) -> None:
        if not method_name or method_name.isspace():
            raise ValueError("Method name cannot be null or whitespace")

        if method_name in self._request_handlers:
            raise ValueError(f"Request handler for method '{method_name}' already exists")

        self._request_handlers[method_name] = _HanderEntry(
            handler=handler, param_type=self._get_and_check_handler_param_type(handler)
        )

    def register_notification_handler(
        self,
        method_name: str,
        handler: Callable[["JsonRpcPeer", Any], Coroutine[Any, Any, Any]],
    ) -> None:
        if not method_name or method_name.isspace():
            raise ValueError("Method name cannot be null or whitespace")

        if method_name in self._notification_handlers:
            raise ValueError(f"Notification handler for method '{method_name}' already exists")

        self._notification_handlers[method_name] = _HanderEntry(
            handler=handler, param_type=self._get_and_check_handler_param_type(handler)
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

        async with self._id_lock:
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
            async with self._id_lock:
                self._pending_requests.pop(id_str, None)

    async def io_loop(self) -> None:
        buffer = bytearray()
        content_length = 0
        headers_complete = False
        encoding = self.default_encoding

        try:
            while self.running:
                try:
                    data = await self.reader.read(4096)
                    if not data:
                        self.running = False
                        break
                except asyncio.CancelledError:
                    self.running = False
                    raise

                buffer.extend(data)

                while True:
                    if not headers_complete:
                        header_end = buffer.find(b"\r\n\r\n")
                        if header_end == -1:
                            break

                        encoding = self.default_encoding

                        headers = buffer[:header_end].decode("ascii")
                        message_too_large = False

                        for line in headers.split("\r\n"):
                            if line.startswith("Content-Length: "):
                                content_length = int(line[16:])

                                if self.max_message_size is not None and content_length > self.max_message_size:
                                    self.logger.warning(
                                        "Message size %d exceeds maximum %d, closing connection",
                                        content_length,
                                        self.max_message_size,
                                    )
                                    message_too_large = True
                                    break

                            elif line.startswith("Content-Type: "):
                                content_type = line[14:]
                                parts = content_type.split(";")
                                for part in parts:
                                    part = part.strip()
                                    if part.startswith("charset="):
                                        charset = part[8:].strip().strip('"')
                                        if charset:
                                            encoding = charset

                        buffer = buffer[header_end + 4 :]
                        headers_complete = True

                        if message_too_large:
                            self.running = False
                            break

                    if headers_complete and len(buffer) >= content_length:
                        body = buffer[:content_length]
                        message = body.decode(encoding)

                        await self.handle_message(message)

                        buffer = buffer[content_length:]
                        headers_complete = False
                        content_length = 0
                    else:
                        break
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            if not self._completion_future.done():
                self._completion_future.set_exception(e)
            return
        finally:
            self.running = False
            if not self._completion_future.done():
                self._completion_future.set_result(True)

    async def handle_message(self, json_str: str) -> None:
        try:
            json_element = json.loads(json_str)

            if isinstance(json_element, list):
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
                    await self._send_message(response)

        except json.JSONDecodeError as ex:
            error_response = JsonRpcErrorResponse(
                error=JsonRpcError(
                    code=JsonRpcErrorCode.PARSE_ERROR,
                    message=str(ex),
                    data=traceback.format_exc(),
                ),
                id=None,
            )
            await self._send_message(error_response)
        except JsonRpcInvalidRequestError as ex:
            error_response = JsonRpcErrorResponse(
                error=JsonRpcError(
                    code=JsonRpcInvalidRequestError.error_code,
                    message=str(ex),
                    data=traceback.format_exc(),
                ),
                id=None,
            )
            await self._send_message(error_response)
        except Exception as ex:
            error_response = JsonRpcErrorResponse(
                error=JsonRpcError(
                    code=JsonRpcErrorCode.INTERNAL_ERROR,
                    message=str(ex),
                    data=traceback.format_exc(),
                ),
                id=None,
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

            case {"id": id_value, "method": _} if id_value is not None:
                request = JsonRpcRequest(**json_element)
                return await self.process_request(request)

            case {"method": _}:
                notification = JsonRpcNotification(**json_element)
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
            async with self._id_lock:
                tcs = self._pending_requests.pop(id_value, None)

        if tcs is not None:
            match json_element:
                case {"error": error_data}:
                    error = JsonRpcError(**error_data)
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
            error = JsonRpcError(**json_element["error"])
            self.logger.warning(
                "Received error with null ID: %s: %s (%s)",
                error.code,
                error.message,
                error.data,
            )

        return None

    async def _call_handler(
        self,
        handler: _HanderEntry,
        params: Any,
    ) -> Any:
        return await handler.handler(self, from_dict(params, handler.param_type))

    async def process_request(self, message: JsonRpcRequest) -> JsonResponseBase:
        if message.method in self._request_handlers:
            handler = self._request_handlers[message.method]
            try:
                result = await self._call_handler(handler, message.params)
                return JsonRpcResponse(id=message.id, result=result)
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
