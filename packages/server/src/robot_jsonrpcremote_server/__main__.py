import argparse
import asyncio
import contextlib
import logging
import os
import threading
from typing import Awaitable, Literal, Sequence

from jsonrpcpeer import JsonRpcPeer

from .__version__ import __version__
from ._endpoint import RobotServerEndpoint
from ._runner import RobotRemoteContext

DEFAULT_PORT = 8271

logger = logging.getLogger("robot_jsonrpcremote_server")

_server: asyncio.AbstractServer | None = None
_server_lock = threading.RLock()
_server_started_event = threading.Event()
_server_stop_event = threading.Event()


def _parse_addresses(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [part.strip() for part in value.split(",") if part.strip()]
    return items or None


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
    else:
        if verbose:
            logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")
        else:
            logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")
    logger.setLevel(level)


def get_server() -> asyncio.AbstractServer | None:
    with _server_lock:
        return _server


def set_server(value: asyncio.AbstractServer | None) -> None:
    with _server_lock:
        global _server
        _server = value


async def handle_client(
    remote_context: RobotRemoteContext,
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, verbose: bool, libraries: Sequence[str] | None
) -> None:
    addr = writer.get_extra_info("peername")
    logger.debug("Client connected from %s", addr)

    peer = JsonRpcPeer(reader, writer)
    endpoint = RobotServerEndpoint(remote_context=remote_context, libraries=libraries, verbose=verbose)
    peer.attach_endpoint(endpoint)

    try:
        await peer.run()
    except Exception:
        # Log and re-raise so unexpected errors surface while keeping per-client context in the log.
        logger.exception("Error handling client %s", addr)
        raise
    finally:
        endpoint.cleanup()
        logger.debug("Client %s disconnected", addr)
        if not writer.is_closing():
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()


async def run_tcp_server(
    remote_context: RobotRemoteContext,
    addresses: Sequence[str],
    port: int,
    verbose: bool,
    libraries: Sequence[str] | None,
) -> None:
    def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> Awaitable[None]:
        return handle_client(remote_context, reader, writer, verbose, libraries)

    server = await asyncio.start_server(client_handler, addresses, port)
    bind_targets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logger.info("Robot JSON-RPC Remote Server listening on %s", bind_targets)

    async with server:
        set_server(server)
        _server_started_event.set()
        _server_stop_event.clear()
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            logger.debug("Server task cancelled; shutting down.")
        finally:
            set_server(None)
            _server_started_event.clear()
            _server_stop_event.set()


async def run_server_async(
    remote_context: RobotRemoteContext,
    mode: Literal["tcp", "pipe"],
    addresses: Sequence[str],
    port: int,
    pipe_name: str,
    libraries: Sequence[str] | None,
    verbose: bool,
) -> None:
    if mode == "tcp":
        await run_tcp_server(remote_context, addresses, port, verbose, libraries)
        return

    raise NotImplementedError(f"Mode '{mode}' is not implemented yet")


def run_server(
    remote_context: RobotRemoteContext,
    mode: Literal["tcp", "pipe"],
    addresses: Sequence[str],
    port: int,
    pipe_name: str,
    libraries: Sequence[str] | None,
    verbose: bool,
) -> None:
    asyncio.run(
        run_server_async(
            remote_context=remote_context,
            mode=mode,
            addresses=addresses,
            port=port,
            pipe_name=pipe_name,
            libraries=libraries,
            verbose=verbose,
        )
    )


def stop_server() -> None:
    server = get_server()
    if server is None:
        return
    loop = server.get_loop()

    def shutdown() -> None:
        # Close the server; once closed, serve_forever() will return.
        server.close()

        async def finalize() -> None:
            await server.wait_closed()

        loop.create_task(finalize())

    # Run shutdown inside the server loop to avoid stopping it before serve_forever() completes.
    loop.call_soon_threadsafe(shutdown)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        # prog="robot-jsonrpcremote-server",
        description="Robot Framework JSON-RPC Remote Server",
        epilog="For more information, visit project page.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"robot-jsonrpcremote-server {__version__}")

    mode_group = parser.add_argument_group("server mode")

    default_mode = os.environ.get("ROBOT_JSONRPC_MODE", "tcp")
    mode_group.add_argument(
        "--mode",
        choices=["tcp", "pipe"],
        default=default_mode,
        help=f"Server mode (default: {default_mode} or ROBOT_JSONRPC_MODE)",
    )

    mode_ex_group = mode_group.add_mutually_exclusive_group()
    mode_ex_group.add_argument(
        "--tcp",
        action="store_const",
        dest="mode",
        const="tcp",
        help="Run server in TCP mode (alias for --mode tcp)",
    )
    mode_ex_group.add_argument(
        "--pipe",
        action="store_const",
        dest="mode",
        const="pipe",
        help="Run server in pipe mode (alias for --mode pipe)",
    )
    mode_ex_group.add_argument(
        "--stdio",
        action="store_const",
        dest="mode",
        const="stdio",
        help="Run server in stdio mode (alias for --mode stdio)",
    )

    tcp_group = parser.add_argument_group(
        "tcp mode settings", description="Configure the listening address and port for TCP connections."
    )
    tcp_group.add_argument(
        "--bind",
        dest="addresses",
        action="append",
        type=str,
        metavar="ADDRESS",
        help="Address to bind (repeatable; comma-separated via ROBOT_JSONRPC_BIND; default: 127.0.0.1)",
    )
    tcp_group.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ROBOT_JSONRPC_PORT", DEFAULT_PORT)),
        help=f"Port number to bind the server (default: {DEFAULT_PORT} or ROBOT_JSONRPC_PORT)",
    )

    pipe_group = parser.add_argument_group("pipe mode settings")
    pipe_group.add_argument(
        "--pipe-name",
        type=str,
        default=os.environ.get("ROBOT_JSONRPC_PIPE_NAME", "robot_jsonrpcremote_pipe"),
        help="Name of the pipe to use (default: robot_jsonrpcremote_pipe or ROBOT_JSONRPC_PIPE_NAME)",
    )

    robot_group = parser.add_argument_group("robot settings", description="Settings for Robot Framework")
    robot_group.add_argument(
        "--pythonpath",
        "-P",
        type=str,
        action="append",
        help="Add a directory to the Python path for Robot Framework",
    )

    parser.add_argument("libraries", metavar="LIBRARY", nargs="*", help="the library to expose via JSON-RPC")

    return parser


def run() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    logger.debug("Verbose mode is enabled.")

    env_addresses = _parse_addresses(os.environ.get("ROBOT_JSONRPC_BIND"))
    addresses = args.addresses or env_addresses or ["127.0.0.1"]

    if args.mode == "tcp":
        logger.info("Server will start on %s:%s", ",".join(addresses), args.port)
    elif args.mode == "pipe":
        logger.info("Server will start with pipe name: %s", args.pipe_name)
    else:
        raise NotImplementedError(f"Mode '{args.mode}' is not supported.")

    logger.debug("Libraries to serve: %s", args.libraries)
    logger.debug("Python path additions: %s", args.pythonpath)

    remote_context = RobotRemoteContext(
        variables=(),
        variablefiles=(),
        pythonpath=args.pythonpath or (),
        outputdir=None,
        output=None,
        report=None,
        log=None,
    )

    server_thread = threading.Thread(
        target=run_server,
        args=(
            remote_context,
            args.mode,
            addresses,
            args.port,
            args.pipe_name,
            args.libraries,
            args.verbose,
        ),
        name="RobotJsonRpcRemoteServerThread",
    )
    server_thread.start()

    _server_started_event.wait(5)
    logger.info("Server is up and running. Press Ctrl+C to stop.")

    if _server is None:
        logger.error("Server failed to start.")
        return

    try:
        remote_context.run()
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
    finally:
        stop_server()

    logger.info("Server is stopping...")
    _server_stop_event.wait(5)
    server_thread.join(5)

    logger.info("Server has stopped.")


if __name__ == "__main__":
    run()
