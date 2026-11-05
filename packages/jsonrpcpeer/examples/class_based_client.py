import asyncio

from class_based_api import AddParams, Calculator, CalculatorLog, LogParams

from jsonrpcpeer import JsonRpcPeer


class PrintingLog(CalculatorLog):
    async def log(self, params: LogParams) -> None:
        print(f"Server log: {params.message}")


async def main() -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", 8888)
    peer = JsonRpcPeer(reader, writer)

    peer.attach_endpoint(PrintingLog())

    peer.start()

    calculator = peer.remote(Calculator)

    result = await calculator.add(AddParams(a=10.0, b=20.0))
    print(f"10 + 20 = {result.result}")

    result = await calculator.add(AddParams(a=5.0, b=5.0))
    print(f"5 + 5 = {result.result}")

    await peer.stop()


if __name__ == "__main__":
    asyncio.run(main())
