"""The interface of the class-based examples, stated once for both sides."""

import dataclasses
from abc import abstractmethod

from jsonrpcpeer import JsonRpcEndpoint, rpc_notification, rpc_request


@dataclasses.dataclass
class AddParams:
    a: float
    b: float


@dataclasses.dataclass
class AddResult:
    result: float


@dataclasses.dataclass
class LogParams:
    message: str


class Calculator(JsonRpcEndpoint):
    """What the server implements and the client calls."""

    @rpc_request("add")
    @abstractmethod
    async def add(self, params: AddParams) -> AddResult: ...


class CalculatorLog(JsonRpcEndpoint):
    """What the client implements and the server calls."""

    @rpc_notification("log")
    @abstractmethod
    async def log(self, params: LogParams) -> None: ...
