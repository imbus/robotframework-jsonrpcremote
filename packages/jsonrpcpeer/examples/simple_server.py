import asyncio

from jsonrpcpeer import JsonRpcPeer


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = JsonRpcPeer(reader, writer)

    # Simple handler with one parameter
    async def add(params: dict[str, int]) -> int:
        return params["a"] + params["b"]

    peer.register_request_handler("add", add)

    await peer.run()


async def main() -> None:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 8888)
    print("Server started on port 8888")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
