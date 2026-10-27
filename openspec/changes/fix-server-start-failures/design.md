# Design

## Context

See proposal.md for the motivation and specs/server/spec.md for the requirements.

**How the server starts today**, in `packages/server/src/robot_jsonrpcremote_server/__main__.py`:

1. `run()` starts the server thread, whose target `run_server()` runs `asyncio.run(run_server_async(...))`.
2. `run_tcp_server()` or `run_stdio_server()` sets `_server_started_event` once the transport is ready.
3. `run()` waits for that event for at most 5 seconds and then logs "Server is up and running" unconditionally. Only afterwards does it check the event; if it is not set, it logs "Server failed to start." and returns, so the process exits with code 0.
4. The error that ended the start is printed only as an unhandled exception of the server thread, with a traceback.

**Entry points:** The console script calls `sys.exit(__main__.run())`; `python -m robot_jsonrpcremote_server` calls `run()` without `sys.exit`. An exit code must therefore come from `run()` raising `SystemExit`, as its argument errors already do through `argparse`.

**stdin in stdio mode:** `_stdio_streams()` passes `sys.stdin.buffer` to `loop.connect_read_pipe()`.

- **Closed stdin:** `sys.stdin` is `None`, and the call fails with an `AttributeError`.
- **Regular file:** the transport rejects it with `ValueError: Pipe transport is for pipes/sockets only.`
- **Character device:** the transport accepts it and registers it with the selector in a later loop callback. For `/dev/null`, epoll rejects that registration with `PermissionError`. The error is only logged, and the stream never delivers data or EOF.
- **What the selectors accept:** On Linux, epoll registers a pipe (also one whose writing end is closed) and a socket, but neither `/dev/null` nor a regular file. kqueue on macOS behaves differently, for example for regular files and terminals.

## Goals / Non-Goals

**Goals:**

- One path for every failed start: one error line in the log, exit code 1, no delay.
- A stdio server fails at start, on every POSIX platform, when its stdin cannot be watched.

**Non-Goals:**

- A start that never finishes, for example a bind that hangs. The main thread waits for it as before.
- Errors after a successful start. They keep their current handling.
- Checking stdout in stdio mode. An unusable stdout already fails `connect_write_pipe()` at start, which this change turns into a proper failed start.

## Decisions

### 1. The server thread records why the start failed; the main thread waits for the outcome

`run_server()` catches the error that ends the server thread before the server is up, records it and lets the thread end, so the error is no longer printed as an unhandled thread exception. Errors after a successful start are re-raised unchanged.

`run()` waits until the server is up or the server thread has ended, instead of waiting a fixed 5 seconds. Only then does it log anything about the outcome.

- **Alternative:** keep the 5-second wait and only fix the exit code. A failed start would still take 5 seconds, and a slow start would still be reported as a failure.

### 2. A failed start logs one error and exits with code 1

If the server is not up, `run()` logs `Server failed to start: <error>` at error level and raises `SystemExit(1)`. That works for both entry points. The traceback is logged at debug level, so `--verbose` still shows it. "Server is up and running" is logged only after a successful start.

- **Why exit code 1:** it is the conventional generic failure code. `argparse` already uses 2 for usage errors, so the two stay distinguishable.

### 3. stdio mode checks its stdin before connecting

`_stdio_streams()` checks stdin before it calls `connect_read_pipe()`, in two steps, and raises a `RuntimeError` that states that stdio mode needs a stdin that can be watched for input, such as a pipe, naming what it found instead:

1. **Type:** stdin must be open and be a pipe, a socket or a terminal. That rejects `/dev/null` and other character devices, regular files and a closed stdin on every platform, whatever its selector accepts.
2. **Watchability:** a selector of the event loop's default type must be able to register stdin. That catches a platform whose selector cannot watch the given kind of stdin, for example a terminal on macOS. A temporary selector is used and closed again; the event loop's own selector is private.

The error then takes the failed-start path of decisions 1 and 2.

- **Alternative:** read an unwatchable stdin on a helper thread, so `/dev/null` behaves like an immediate EOF and the server exits with code 0. Rejected: a misconfigured container would look like a normal end.
- **Alternative:** detect the failed registration after connecting. That needs the event loop's private selector.

## Risks / Trade-offs

- **[Changed exit code]** A script that started the server and ignored a failed start now sees exit code 1. → A failed start was never a success; the server README documents the exit code.
- **[The probe uses a temporary selector]** The event loop could use a different selector than `selectors.DefaultSelector`, for example with a custom event loop policy. → The server always runs the default policy through `asyncio.run()`.
- **[Terminal on stdin]** A terminal is accepted where the selector can watch it, so stdio mode can still be tried by hand on Linux. Where it cannot, the start fails with the same error.
