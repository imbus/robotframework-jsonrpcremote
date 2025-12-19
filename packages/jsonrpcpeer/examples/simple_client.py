import asyncio

from jsonrpcpeer import JsonRpcPeer


async def main() -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", 8888)
    peer = JsonRpcPeer(reader, writer)
    peer.start()

    # 1. Send a request using a dataclass
    # This matches the 'AddParams' expected by the server

    result = await peer.send_request("add", {"a": 10, "b": 20})
    print(f"10 + 20 = {result}")

    # 2. Send a request using a dictionary
    # You can also pass a dict if you don't want to define a dataclass
    result_dict = await peer.send_request("add", {"a": 5, "b": 5})
    print(f"5 + 5 = {result_dict}")

    # 3. Send a notification
    await peer.send_notification("log", {"message": "Client connected!"})


if __name__ == "__main__":
    asyncio.run(main())
