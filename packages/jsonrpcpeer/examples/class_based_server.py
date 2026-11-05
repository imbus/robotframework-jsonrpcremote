import asyncio

from class_based_api import AddParams, AddResult, Calculator, CalculatorLog, LogParams

from jsonrpcpeer import JsonRpcPeer


class WorkingCalculator(Calculator):
    async def add(self, params: AddParams) -> AddResult:
        await self.remote(CalculatorLog).log(LogParams(message=f"Adding {params.a} and {params.b}"))
        return AddResult(result=params.a + params.b)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = JsonRpcPeer(reader, writer)

    peer.attach_endpoint(WorkingCalculator())

    await peer.run()


async def main() -> None:
    server = await asyncio.start_server(handle_client, "127.0.0.1", 8888)
    print("Server started on port 8888")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
