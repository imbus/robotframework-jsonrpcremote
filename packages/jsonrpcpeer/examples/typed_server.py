import asyncio
import dataclasses

from jsonrpcpeer import JsonRpcPeer


@dataclasses.dataclass
class AddParams:
    a: float
    b: float


@dataclasses.dataclass
class AddResult:
    result: float


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = JsonRpcPeer(reader, writer)

    async def add(params: AddParams) -> AddResult:
        return AddResult(result=params.a + params.b)

    peer.register_request_handler("add", add)
    try:
        await peer.run()
    except ConnectionResetError:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")


async def main() -> None:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 8888)
    print("Server started on port 8888")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
