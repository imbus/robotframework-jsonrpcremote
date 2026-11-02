# Design

## Context

See proposal.md for the motivation. The cycle comes about like this when the reset arrives after the client has written its first request:

1. asyncio's `StreamReaderProtocol.connection_lost` stores the same `ConnectionResetError`, called B here, in the reader and in the future behind `writer.wait_closed()`.
2. The peer's read loop gets B from the reader and fails the waiting request with a `JsonRpcConnectionClosedError`, called A here, with `A.__cause__ = B`. The peer's spec requires that cause. The read loop also sets B as the exception of the peer's completion, for which nobody waits during a start (CLIENT-7).
3. `_Session._run_client` catches A and calls `close_connection()` inside its `except` block.
4. `wait_closed()` raises B again. A is being handled at that moment, so Python sets `B.__context__ = A`, and `contextlib.suppress` swallows B. Python avoids cycles only along `__context__`, so the cycle from A through `__cause__` to B and through `__context__` back to A stays.
5. `_connect` raises A in Robot Framework's thread. `ErrorDetails._remove_robot_traces` in `robot/utils/error.py` follows `__context__` and `__cause__` recursively, without remembering where it has been, until `RecursionError`. Because that happens in Robot Framework's own error handling, it does not become a keyword failure. Only the outermost handler catches it, and that ends the run.

A reset that arrives before the request is written usually fails the write with a new `ConnectionResetError('Connection lost')`, which is not linked to B. There is no cycle then, so only some resets crash the run.

## Goals / Non-Goals

**Goals:**

- The error of a failed start has no cycle, and keeps the reset as its cause.
- The report of a failed start still comes after the connection is closed, as the requirement "A failed session start releases its resources" says.

**Non-Goals:**

- A cycle check in Robot Framework. It would also protect against other sources, but it is outside this project and does not help the released versions.
- Changing the message of the failure, or what connect retry does with it.

## Decisions

### 1. The cleanup of a failed start runs after the `except` block

```python
try:
    try:
        await self._start_peer()

        await self._initialize_server()
    except Exception as e:
        self.start_error = e
    if self.start_error is not None:
        # Not in the except block: wait_closed() can raise the cause of the start error again, and
        # Python would make the start error its context, a cycle that crashes Robot Framework.
        with contextlib.suppress(Exception):
            await self.close_connection()
        raise self.start_error
finally:
    self.initialized.set()
```

No exception is being handled when `wait_closed()` raises B, so B gets no context and the chain stays A, B. The connection is still closed before `initialized` hands the failure to the caller.

The other call of `close_connection()`, in the `finally` of a started session, cannot build this cycle: the exception being handled there is B itself, which Python does not chain to itself, or a cancellation, which has no cause.

Alternatives considered:

- **Drop `__cause__` from A:** the requirement "Cause of the closed connection is preserved" and the messages of lost connections need it.
- **Clear `B.__context__` before raising A:** repairs the result instead of the cause, and every future cleanup in an `except` block would need the same.
- **Wait for the close in a separate task inside `close_connection()`:** B would then never be raised in the caller, but that is more code for one call site.

### 2. The peer retrieves the exception of its completion

`_completion()` adds the done callback that already retrieves the error of the writer's close, `_closing_done`, to the completion future. The callback gets a name that fits both uses, `_retrieve_exception`. Retrieving marks the exception as seen, so asyncio does not report it, and a later `await` still raises it.

The alternative from the backlog sketch, retrieving it in `_run_client` after a failed start, leaves a gap: the read loop can still be running at that moment and set the exception later. It would also leave the same report for every other user of the peer.

### 3. `ServerControl` waits until the port no longer accepts connections

`start_jsonrpc_server` remembers the port. `stop_jsonrpc_server`, `kill_jsonrpc_server` and `wait_for_jsonrpc_server_to_exit` end by connecting in a loop until a connection attempt fails, and raise if the port is still open after 10 seconds.

Each attempt has a timeout of 0.2 seconds, and a timeout counts as closed: a listening port on the loopback address answers at once, while a connection attempt to a closed port on Windows takes about 2 seconds, because TCP tries it three times. A stop therefore costs at most 0.2 seconds more on Windows, and nothing on POSIX.

Alternatives considered:

- **Start the real interpreter instead of the launcher:** needs the private `sys._base_executable` and the variable `__PYVENV_LAUNCHER__`, and would test something users do not run.
- **Stop the process tree:** `psutil` is no dependency of the project, and the suites only need the port to be closed.

### 4. The Robot tests run in a nested process, against a server that resets

A regression crashes Robot Framework, so the new suite `atests/connection_reset.robot` runs its scenarios with `NestedRobot`, in the way of `atests/failure_modes.robot`. A crash then shows as exit code 255 of the nested run. That fails one test and leaves the outer run alive.

The new library `atests/ResetServer.py` listens on a port, reads the first bytes of a connection and closes it with a linger time of zero. The client has then written its request, so the order of the events is fixed. It uses plain sockets, because `socketserver` shuts a socket down before closing it, which gives a clean close instead of a reset. As in `tests/fake_server.py`, the linger value is packed as `HH` on Windows and `ii` elsewhere. It sets `SO_REUSEADDR` only on POSIX, as asyncio's servers do.

The import scenario reuses `atests/_nested/failing_import.robot`. The scenario of a later session needs a working first session, so it has its own nested suite, which replaces the real server with the reset server on the same port between its tests.

The unit tests use a new scripted answer of `tests/fake_server.py`, `RESET_CONNECTION`, so that a test can reset at an exact point of the handshake without threads or timing.

## Risks / Trade-offs

- [A later change calls `close_connection()` in an `except` block again] → A unit test checks that the chain has no cycle, and a comment at the call says why it is where it is.
- [Exceptions with cycles from other sources still crash Robot Framework] → Out of scope here; the missing check can be reported to Robot Framework.
- [The 0.2 second timeout counts a very slow connection to a server that is still listening as closed] → The stop then returns early, as it does today; a test could fail as it can today, but this needs a machine that takes longer than that for a loopback connection.
