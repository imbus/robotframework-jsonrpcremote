# Proposal

## Why

In stdio mode the server's stdout is the protocol channel, so anything else written to it corrupts the stream. Robot Framework captures `print()` inside a keyword, so that case works, even with the printing `JsonRpcRemote.Echo` library. Everything that writes to file descriptor 1 directly breaks the connection, though: a child process started with `os.system()` or with `subprocess` without capturing its output, a C extension, or a thread that prints outside a keyword call. The client then cannot decode the frame (`JSONDecodeError`), and the keyword call never gets its response. A keyword that runs `os.system("echo from-child-process")` over stdio reproduces it.

Test setups start tools and applications under test all the time, so stdio mode is fragile exactly where it is meant to be used. The READMEs say that hosted libraries must not `print()`, which is too strict for `print()` and too weak for everything else.

Found in the project review of 2026-10-27 (item NET-6).

## What Changes

- **Protected protocol channel:** when stdio mode starts, the server moves the protocol channel to a private duplicate of the original stdout and points file descriptor 1 and `sys.stdout` at stderr. Output of libraries, child processes and C code then ends up on the server's stderr; only protocol frames reach the client.
- **Docs:** the stdio notes on the documentation site state that output written to stdout appears on the server's stderr, instead of forbidding `print()`, with a runnable example.
- **Tests:** a unit test for the redirection; a Robot test over stdio runs a keyword whose child process writes to stdout, and the call succeeds.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds the requirement that, in stdio mode, output written to the server process's stdout does not reach the protocol channel.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/__main__.py` (`_stdio_streams()`, `run_stdio_server()`).
- **Platforms:** POSIX only, like stdio mode itself.
- **Behavior:** output that used to corrupt the stream now appears on the server's stderr.
- **Docs:** the stdio notes on the documentation site.
- **Tests:** the Robot test carries the tag `posix`.
- **Order:** independent of the other changes.
