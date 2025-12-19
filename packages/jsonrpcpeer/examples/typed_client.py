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


async def main() -> None:
    peer = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", 8888))
    peer.start()

    # 1. Send a request using a dataclass
    # This matches the 'AddParams' expected by the server
    result = await peer.send_request_typed(AddResult, "add", AddParams(a=10.0, b=20.0))
    print(f"10 + 20 = {result.result}")

    # 2. Send a request using a dictionary
    # You can also pass a dict if you don't want to define a dataclass
    result_dict = await peer.send_request_typed(dict, "add", {"a": 5.0, "b": 5.0})
    print(f"5 + 5 = {result_dict['result']}")

    # 3. Send a notification
    await peer.send_notification("log", {"message": "Client connected!"})


if __name__ == "__main__":
    asyncio.run(main())
