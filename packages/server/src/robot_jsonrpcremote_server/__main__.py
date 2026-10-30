import argparse
import asyncio
import contextlib
import logging
import os
import selectors
import stat
import sys
import threading
from typing import Any, Awaitable, Callable, Literal, Sequence

from jsonrpcpeer import JsonRpcPeer

from .__version__ import __version__
from ._endpoint import RobotServerEndpoint, end_connection
from ._runner import RobotRemoteContext
from ._signals import patch_robot_signal_handling

DEFAULT_PORT = 8271

logger = logging.getLogger("robot_jsonrpcremote_server")

_server: asyncio.AbstractServer | None = None
_server_lock = threading.RLock()
_server_started_event = threading.Event()
_server_stop_event = threading.Event()
# Why the server thread ended before the server was up; read by run().
_server_start_error: BaseException | None = None

# Stop hook for transports without an asyncio.AbstractServer (e.g. stdio).
_loop: asyncio.AbstractEventLoop | None = None
_stop_callable: Callable[[], None] | None = None

# The connected clients by the task that handles them; only used on the server's event loop.
_clients: dict["asyncio.Task[Any]", tuple[JsonRpcPeer, RobotServerEndpoint]] = {}

# How long a stopping server waits for the requests in progress, for all clients together.
_STOP_GRACE_PERIOD = 5.0


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


def _server_has_been_up() -> bool:
    """Whether the server has been up: a transport sets the stop event only when it ends after being up."""
    return _server_started_event.is_set() or _server_stop_event.is_set()


def set_transport_stop(loop: asyncio.AbstractEventLoop | None, stop: Callable[[], None] | None) -> None:
    """Register (or clear) the transport's stop hook so stop_server() can stop it uniformly."""
    with _server_lock:
        global _loop, _stop_callable
        _loop = loop
        _stop_callable = stop


async def handle_client(
    remote_context: RobotRemoteContext,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    verbose: bool,
    libraries: Sequence[str] | None,
) -> None:
    addr = writer.get_extra_info("peername")
    logger.debug("Client connected from %s", addr)

    peer = JsonRpcPeer(reader, writer)
    endpoint = RobotServerEndpoint(remote_context=remote_context, libraries=libraries, verbose=verbose)
    peer.attach_endpoint(endpoint)
    task = asyncio.current_task()
    assert task is not None
    _clients[task] = (peer, endpoint)

    try:
        await peer.run()
    except Exception:
        # Log and re-raise so unexpected errors surface while keeping per-client context in the log.
        logger.exception("Error handling client %s", addr)
        raise
    finally:
        # Release any libraries this client imported from the shared keyword store,
        # in case it disconnected without the finalize/shutdown/exit handshake.
        await endpoint.finalize_all()
        endpoint.cleanup()
        logger.debug("Client %s disconnected", addr)
        if not writer.is_closing():
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        _clients.pop(task, None)


async def close_clients() -> None:
    """Let the requests in progress deliver their responses, then close every client connection."""
    clients = dict(_clients)
    if not clients:
        return
    logger.debug("Closing %d client connection(s).", len(clients))
    await asyncio.gather(*(endpoint.wait_idle(_STOP_GRACE_PERIOD) for _, endpoint in clients.values()))
    for peer, _ in clients.values():
        end_connection(peer)
    await asyncio.wait(list(clients), timeout=_STOP_GRACE_PERIOD)


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

    stop_requested = asyncio.Event()
    async with server:
        set_server(server)
        set_transport_stop(asyncio.get_running_loop(), stop_requested.set)
        _server_started_event.set()
        _server_stop_event.clear()
        try:
            # Not serve_forever(): once stopped, it waits for every client connection to close,
            # which on Python >= 3.12.1 would block the client shutdown below. The server
            # accepts connections since start_server().
            await stop_requested.wait()
        except asyncio.CancelledError:
            logger.debug("Server task cancelled; shutting down.")
        finally:
            set_server(None)
            set_transport_stop(None, None)
            # Accept no new connections, then close the ones there are before `async with`
            # waits for them.
            server.close()
            await close_clients()
            _server_started_event.clear()
            _server_stop_event.set()


def _check_stdio_stdin() -> None:
    """Raise unless stdin is open and the event loop can watch it for input, as stdio mode needs.

    An unwatchable stdin such as /dev/null would otherwise never deliver data or EOF.
    """
    needs = "stdio mode needs a stdin that can be watched for input, such as a pipe"
    if sys.stdin is None:
        raise RuntimeError(f"{needs}, but stdin is closed")
    try:
        fd = sys.stdin.fileno()
        mode = os.fstat(fd).st_mode
    except (OSError, ValueError):
        raise RuntimeError(f"{needs}, but stdin is closed") from None

    # The type rule holds on every platform, whatever its selector would accept.
    if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode) or os.isatty(fd)):
        if stat.S_ISREG(mode):
            found = "a regular file"
        elif stat.S_ISCHR(mode):
            found = "a character device such as /dev/null"
        else:
            found = "neither a pipe, a socket nor a terminal"
        raise RuntimeError(f"{needs}, but stdin is {found}")

    # Not every selector can watch every kind of stdin, for example a terminal on macOS.
    with selectors.DefaultSelector() as probe:
        try:
            probe.register(fd, selectors.EVENT_READ)
        except (OSError, ValueError) as error:
            raise RuntimeError(f"{needs}, but the event loop cannot watch it: {error}") from error


async def _stdio_streams() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Wrap stdin/stdout as an asyncio reader/writer pair (POSIX only; binary buffers)."""
    if sys.platform == "win32":
        raise RuntimeError("stdio mode is not supported on Windows; use --tcp instead.")
    _check_stdio_stdin()

    loop = asyncio.get_running_loop()

    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)

    write_transport, write_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout.buffer)
    writer = asyncio.StreamWriter(write_transport, write_protocol, reader, loop)

    return reader, writer


async def run_stdio_server(
    remote_context: RobotRemoteContext,
    verbose: bool,
    libraries: Sequence[str] | None,
) -> None:
    reader, writer = await _stdio_streams()
    loop = asyncio.get_running_loop()
    logger.info("Robot JSON-RPC Remote Server serving on stdio")

    client_task = asyncio.ensure_future(handle_client(remote_context, reader, writer, verbose, libraries))
    stopping: set["asyncio.Task[None]"] = set()

    async def close_client() -> None:
        await close_clients()
        # Fallback, if the client did not end within the grace period.
        if not client_task.done():
            client_task.cancel()

    def _stop() -> None:
        # Called via stop_server() on SIGINT/SIGTERM. Keeps a reference to the task until it is done.
        task = loop.create_task(close_client())
        stopping.add(task)
        task.add_done_callback(stopping.discard)

    set_transport_stop(loop, _stop)
    _server_started_event.set()
    _server_stop_event.clear()
    try:
        await client_task
    except asyncio.CancelledError:
        logger.debug("stdio client task cancelled; shutting down.")
    finally:
        set_transport_stop(None, None)
        _server_started_event.clear()
        _server_stop_event.set()
        # stdio has a single client: on EOF/stop, stop the runner so the main thread exits.
        remote_context.stop()


async def run_server_async(
    remote_context: RobotRemoteContext,
    mode: Literal["tcp", "stdio", "pipe"],
    addresses: Sequence[str],
    port: int,
    pipe_name: str,
    libraries: Sequence[str] | None,
    verbose: bool,
) -> None:
    if mode == "tcp":
        await run_tcp_server(remote_context, addresses, port, verbose, libraries)
        return

    if mode == "stdio":
        await run_stdio_server(remote_context, verbose, libraries)
        return

    raise NotImplementedError(f"Mode '{mode}' is not implemented yet")


def run_server(
    remote_context: RobotRemoteContext,
    mode: Literal["tcp", "stdio", "pipe"],
    addresses: Sequence[str],
    port: int,
    pipe_name: str,
    libraries: Sequence[str] | None,
    verbose: bool,
) -> None:
    global _server_start_error
    try:
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
    except Exception as error:
        if _server_has_been_up():
            raise
        # A failed start: run() reports it, so the thread does not print it as unhandled.
        _server_start_error = error


def stop_server() -> None:
    with _server_lock:
        loop = _loop
        stop = _stop_callable
    if loop is None or stop is None:
        return
    # Run the transport's stop hook inside its own loop. For TCP this closes the
    # server (serve_forever() then returns); for stdio it feeds EOF / cancels the
    # single client task.
    loop.call_soon_threadsafe(stop)


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
        choices=["tcp", "stdio", "pipe"],
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
        help="Run server in pipe mode (alias for --mode pipe) [planned, not yet implemented]",
    )
    mode_ex_group.add_argument(
        "--stdio",
        action="store_const",
        dest="mode",
        const="stdio",
        help="Run server in stdio mode (alias for --mode stdio): serve a single client over stdin/stdout (POSIX only)",
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
        metavar="PATH",
        help="Add a directory to the Python path (repeatable), like robot's --pythonpath",
    )
    robot_group.add_argument(
        "--variable",
        type=str,
        action="append",
        metavar="name:value",
        help="Set an individual variable (repeatable), like robot's --variable (-v is taken by --verbose)",
    )
    robot_group.add_argument(
        "--variablefile",
        "-V",
        type=str,
        action="append",
        metavar="PATH",
        help="Load variables from a file (repeatable), like robot's --variablefile",
    )
    robot_group.add_argument(
        "--outputdir",
        "-d",
        type=str,
        metavar="DIR",
        help="Set ${OUTPUT_DIR} for the libraries (default: the current directory); the server writes no output files",
    )

    parser.add_argument("libraries", metavar="LIBRARY", nargs="*", help="the library to expose via JSON-RPC")

    return parser


def run() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    logger.debug("Verbose mode is enabled.")

    if args.mode not in ("tcp", "stdio"):
        parser.error(
            f"server mode '{args.mode}' is not supported yet; only 'tcp' and 'stdio' are available "
            "('--pipe' is planned)."
        )

    env_addresses = _parse_addresses(os.environ.get("ROBOT_JSONRPC_BIND"))
    addresses = args.addresses or env_addresses or ["127.0.0.1"]

    if args.mode == "stdio":
        logger.info("Server will start in stdio mode.")
    else:
        logger.info("Server will start on %s:%s", ",".join(addresses), args.port)

    logger.debug("Libraries to serve: %s", args.libraries)
    logger.debug("Python path additions: %s", args.pythonpath)

    remote_context = RobotRemoteContext(
        variables=args.variable or (),
        variablefiles=args.variablefile or (),
        pythonpath=args.pythonpath or (),
        outputdir=args.outputdir,
        # No output files: Robot Framework writes none with output, report and log set to None.
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

    # Wait until the server is up, or until its thread has ended because the start failed.
    while server_thread.is_alive() and not _server_started_event.wait(0.1):
        pass

    if not _server_has_been_up():
        reason = _server_start_error if _server_start_error is not None else "the server thread ended"
        logger.error("Server failed to start: %s", reason)
        if _server_start_error is not None:
            logger.debug("Details of the failed start:", exc_info=_server_start_error)
        raise SystemExit(1)

    logger.info("Server is up and running. Press Ctrl+C to stop.")

    # Let SIGINT/SIGTERM stop the embedded Robot runner gracefully instead of Robot's
    # noisy "Second signal will force exit." abort. The hook loop ends normally and the
    # process exits cleanly.
    patch_robot_signal_handling(remote_context.stop)

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
