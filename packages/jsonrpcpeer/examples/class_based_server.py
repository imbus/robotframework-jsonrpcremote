import asyncio
import dataclasses

from jsonrpcpeer import JsonRpcPeer, rpc_request


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

    @rpc_request("add")
    async def _add(self, params: AddParams) -> AddResult:
        await self.log(f"Adding {params.a} and {params.b}")
        return AddResult(result=params.a + params.b)

    async def log(self, message: str) -> None:
        if self.rpc_peer is not None:
            await self.rpc_peer.send_notification("log", LogParams(message=message))


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = JsonRpcPeer(reader, writer)

    peer.attach_endpoint(Calculator())

    await peer.run()


async def main() -> None:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 8888)
    print("Server started on port 8888")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
