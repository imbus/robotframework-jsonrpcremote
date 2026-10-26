# Tasks

## 1. Runner rejects and drains

- [ ] 1.1 In `_runner.py`, add a lock and a closed flag. Submitting `import_library`, `run_keyword` or `finalize_library` raises `RuntimeError("server is shutting down")` when the context is stopped or closed. When the hook loop exits, it marks the context closed and fails every queued command with that error. `stop()` stays lock-free (design decision 1). Verify with unit tests that drive the hook loop on a separate thread without Robot: a command running when `stop()` is called completes with its result, a command queued behind it fails with "server is shutting down" and is never executed, and a submission after `stop()` fails immediately

## 2. Track requests and close clients

- [ ] 2.1 Count the running request handlers in `RobotServerEndpoint` and add `wait_idle(timeout)` (design decision 2); verify with unit tests: `wait_idle` returns once a running handler has finished, and returns `False` after the timeout while a handler is still running
- [ ] 2.2 Register the `(peer, endpoint)` pair of each client in `handle_client`, and run the client shutdown in `run_tcp_server` after `serve_forever()` ends and before `async with server` ends: wait until idle with a grace period of 5 seconds, end each connection as the `exit` handler does, then wait for the client tasks (design decisions 3, 4, 6); verify through the end-to-end tests in group 3
- [ ] 2.3 Apply the same sequence to the single client of `run_stdio_server`, cancelling its task only as a fallback (design decision 5); verify that the existing `stdio` suites still pass and that a `stdio` server whose stdin is closed still exits with code 0
- [ ] 2.4 Add the section "Stopping the server" to `packages/server/README.md` (design decision 7); verify that it matches the behavior asserted in the tests

## 3. End-to-end

- [ ] 3.1 Add a keyword to the probe library from `fix-client-lost-connection` that sends SIGTERM to its own server process, sleeps briefly and returns a value; verify it through 3.2
- [ ] 3.2 Add a Robot suite tagged `posix` on port 8276 using `IsolatedServerControl.py`, and verify it passes on Linux and macOS:
  - idle client: with a client session open, `Stop Jsonrpc Server` ends with exit code 0 and without the kill fallback, and the client's next call fails with the lost-connection message;
  - running keyword: the self-terminating keyword's caller receives the returned value, and the server then exits with code 0 without the kill fallback
- [ ] 3.3 Run the shutdown suites and the server unit tests once with Python 3.13 in an environment outside the repository (for example `UV_PROJECT_ENVIRONMENT=/tmp/jsonrpcremote-py313 uv run --python 3.13 --all-packages robotcode run …`), since CI only covers 3.10; verify they pass

## 4. Integration checks

- [ ] 4.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 4.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [ ] 4.3 Commit code, tests, README and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `fix(server): close client connections when stopping`, a body that explains the hang and the new stop sequence, and `Refs #2`; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`, which creates `openspec/specs/server/spec.md`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-server-shutdown-with-clients`.
