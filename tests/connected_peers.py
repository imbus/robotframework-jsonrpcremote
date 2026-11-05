"""Two started peers on a real connection."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from jsonrpcpeer import JsonRpcPeer


@dataclass
class ConnectedPeers:
    left: JsonRpcPeer
    right: JsonRpcPeer


@asynccontextmanager
async def connected_peers() -> AsyncIterator[ConnectedPeers]:
    accepted: asyncio.Queue[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = asyncio.Queue()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await accepted.put((reader, writer))

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    left = JsonRpcPeer(*await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1]))
    right = JsonRpcPeer(*await asyncio.wait_for(accepted.get(), 2))
    left.start()
    right.start()
    try:
        yield ConnectedPeers(left, right)
    finally:
        # Close both ends first: wait_closed() waits for every connection of the server.
        await left.stop()
        await right.stop()
        server.close()
        await asyncio.wait_for(server.wait_closed(), 5)
