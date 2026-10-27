# Design

## Context

See proposal.md for the motivation and specs/server/spec.md for the requirements.

**The current stop sequence** in `packages/server/src/robot_jsonrpcremote_server/`:

1. SIGTERM/SIGINT reaches Robot's signal monitor, which `_signals.py` patches to call `RobotRemoteContext.stop()`.
2. `stop()` sets `_stopped`. The hook loop runs on the main thread, as a Robot keyword. It finishes the command it is executing and then exits, leaving any queued commands unprocessed.
3. `remote_context.run()` returns. `run()` calls `stop_server()`, which schedules `server.close` on the server thread's loop.
4. `server.close` cancels `serve_forever()`, which then calls `close()` and awaits `wait_closed()` itself before it ends. `async with server` calls `wait_closed()` again.

**Why it hangs**, depending on the Python version:

- **Python ≥ 3.12.1:** `wait_closed()` waits for all client connections. Nobody closes them, so `serve_forever()` never ends, the non-daemon server thread blocks forever and the process never exits. Requests that arrive meanwhile are queued for a runner that is gone and are never answered.
- **Python 3.10:** `wait_closed()` returns immediately. `asyncio.run` then cancels the `handle_client` tasks. Their `finally` calls `endpoint.finalize_all()`, which queues commands for the stopped runner and waits forever. Same result.

**Two existing mechanisms to reuse:**

- **Ending a client connection:** The `exit` notification handler shows how to end one connection: set `peer.running = False` and call `peer.reader.feed_eof()`. The read loop ends, and `auto_close` closes the writer.
- **Response timing:** In `JsonRpcPeer`, a request handler's return value is serialized and written to the transport in the same task step as the handler's return. There is no `await` between the two.

## Goals / Non-Goals

**Goals:**

- The process exits on SIGTERM/SIGINT whether or not clients are connected, on every supported Python version.
- Nothing waits on a stopped runner, and no request stays unanswered.
- The result of the keyword that was running when the stop began reaches its client.

**Non-Goals:**

- Interrupting a running keyword. Robot runs it synchronously, so a hung keyword still delays the stop until it returns or the process is killed.
- A configurable grace period. A fixed internal bound is enough for flushing results.
- The library leak when a client disconnects during `import_library` (backlog SERVER-6).

## Decisions

### 1. The runner rejects and drains under a lock; `stop()` stays signal-safe

- **`stop()`** still only sets the event. It runs inside a signal handler on the main thread, which may at that moment hold any lock the hook loop uses, so it must not take one.
- **Submitting** (`import_library`, `run_keyword`, `finalize_library`) takes a lock. If the context is stopped or closed, it raises `RuntimeError("server is shutting down")`; otherwise it enqueues.
- **When the hook loop exits,** it takes the same lock, marks the context closed, and fails every command still in the queue with the same error.
- **Why no command can slip through:** A command is either picked up by the loop before it saw the stop, failed by the drain, or rejected on submit.

### 2. Endpoints track requests in progress

`RobotServerEndpoint` counts the requests whose handlers are running. Each handler increments the count on entry and decrements it in `finally`. When the count drops to zero, an `asyncio.Event` is set. A `wait_idle(timeout)` coroutine waits for that event.

- **Why this proves the response was written:** Because of the peer's write-in-the-same-step behavior (see Context), "idle" observed from another task means every response has been written to the transport buffer.
- **Regression guard:** The end-to-end test for "result of a running keyword is delivered" covers this.

### 3. Registry of active clients

`handle_client` registers its `(peer, endpoint)` pair when it starts and removes it in its `finally`. The stop sequence works on a snapshot of the registry.

### 4. Client shutdown runs inside `run_tcp_server`, before `async with` ends

`run_tcp_server` no longer waits in `serve_forever()`. Once it is cancelled, `serve_forever()` awaits `wait_closed()` itself, which on ≥ 3.12.1 waits for every client connection, so nothing after it would run while a client is connected. Instead, the TCP stop hook sets an `asyncio.Event`, and `run_tcp_server` waits for it; the server already accepts connections after `start_server()`. Once the event is set, and before leaving `async with server`, `run_tcp_server` closes the listener with `server.close()`, so no new connections are accepted, and awaits a coroutine that runs for all registered clients:

1. Wait until the endpoint is idle, bounded by a fixed grace period of 5 seconds for all clients together.
2. End the connection as the `exit` handler does: `peer.running = False` and `peer.reader.feed_eof()`.
3. Wait for the client tasks to finish, bounded.

- **Why there:** On 3.10 the clients are closed before `asyncio.run` starts cancelling tasks. On ≥ 3.12.1 `wait_closed()` returns because no connection is left.
- **Alternative:** keep `serve_forever()` and let the stop hook start the client shutdown as a task, which `run_tcp_server` awaits once `serve_forever()` has ended. That also works on both versions, but the task then runs alongside the `wait_closed()` inside `serve_forever()`, which has more moving parts. A task that `run_tcp_server` does not await would be cancelled on 3.10 by `asyncio.run` together with the clients, which cuts the drain short.

### 5. stdio uses the same sequence for its single client

`run_stdio_server`'s stop hook first waits for the endpoint to become idle (the same bound) and then feeds EOF. It cancels the client task only as a fallback, if the client is still running after the bound.

### 6. Disconnect cleanup does not wait on a stopped runner

`endpoint.finalize_all()` keeps calling `remote_context.finalize_library()`. Once the runner is stopped, that raises at once (decision 1) and is logged at debug level, so the `finally` of `handle_client` completes promptly.

### 7. Documentation

`packages/server/README.md` gets a section "Stopping the server": what happens to running, waiting and new requests, and that the process exits with code 0.

## Risks / Trade-offs

- **[A request arriving at the very last moment]** If a request arrives after its endpoint was seen idle but before its connection is ended, it may get no answer. The client then reports it as lost while running, although the server never executed it. → The window is a few milliseconds during an ongoing stop.
- **[Hung keyword]** A keyword that never returns blocks the stop, because the runner cannot interrupt it. → It is still killed when the process is killed, as Kubernetes does after the grace period. This is documented.
- **[Relying on the peer's write timing]** Decision 2 depends on `JsonRpcPeer` writing a response in the same step as the handler returns. → It is documented here and guarded by the end-to-end test.
- **[CI only runs Python 3.10]** The hang on ≥ 3.12.1 would not be caught. → The tasks include a manual run with Python 3.13; backlog TEST-2 adds a CI matrix.
