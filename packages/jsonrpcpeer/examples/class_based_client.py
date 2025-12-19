import asyncio
import dataclasses

from jsonrpcpeer import JsonRpcPeer, rpc_notification


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


class Calculator:
    def __init__(self) -> None:
        self.rpc_peer: JsonRpcPeer | None = None

    async def add(self, a: float, b: float) -> float:
        if self.rpc_peer is not None:
            return (await self.rpc_peer.send_request_typed(AddResult, "add", AddParams(a=a, b=b))).result
        raise RuntimeError("RPC peer not attached")

    @rpc_notification("log")
    async def _log(self, params: LogParams) -> None:
        print(f"Server log: {params.message}")


async def main() -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", 8888)
    peer = JsonRpcPeer(reader, writer)

    calculator = Calculator()
    peer.attach_endpoint(calculator)

    peer.start()

    result = await calculator.add(10.0, 20.0)
    print(f"10 + 20 = {result}")

    result = await calculator.add(5.0, 5.0)
    print(f"5 + 5 = {result}")

    # 3. Send a notification
    await peer.send_notification("log", {"message": "Client connected!"})




if __name__ == "__main__":
    asyncio.run(main())
