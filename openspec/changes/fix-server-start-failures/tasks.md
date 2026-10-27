# Tasks

## 1. Failed starts

- [ ] 1.1 In `run_server()`, record the error that ends the server thread before the server is up and let the thread end without re-raising it; errors after a successful start are re-raised unchanged. In `run()`, wait until the server is up or its thread has ended instead of a fixed 5 seconds, log "Server is up and running" only after a successful start, and on a failed start log `Server failed to start: <error>` at error level, the traceback at debug level, and raise `SystemExit(1)` (design decisions 1, 2). Verify with a test in `tests/unit/test_server_cli.py` that starts the real server as a subprocess on a port another socket is listening on: it exits with code 1 within 5 seconds of its start, stderr contains `Server failed to start` and the address, and it does not contain `up and running`
- [ ] 1.2 In `packages/server/README.md`, state that a server that cannot start logs the reason and exits with exit code 1; verify that the wording matches the test of 1.1

## 2. stdin in stdio mode

- [ ] 2.1 In `_stdio_streams()`, before connecting, raise a `RuntimeError` stating that stdio mode needs a stdin that can be watched for input, such as a pipe, when stdin is closed, is not a pipe, a socket or a terminal, or cannot be registered with a temporary selector of the default type (design decision 3). Verify with POSIX-only unit tests that call `_stdio_streams()` with `sys.stdin` replaced: `/dev/null`, a regular file and a closed stdin each raise that error, and a pipe is connected
- [ ] 2.2 Add POSIX-only tests to `tests/unit/test_server_cli.py` that start the real server in stdio mode as a subprocess: with stdin `/dev/null` and with a regular file it exits with code 1 within 5 seconds and stderr contains `Server failed to start` and the stdin error; with a pipe whose writing end is already closed it exits with code 0
- [ ] 2.3 In the stdio notes of `packages/server/README.md`, state that stdio mode needs a pipe or socket on stdin and that, for example, a Docker container has to be started with `-i`; verify that the wording matches the tests of 2.2

## 3. Integration checks

- [ ] 3.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 3.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [ ] 3.3 Commit code, tests, README and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `fix(server): fail fast when the server cannot start`, a body that explains both problems and the new behavior, without `Refs #2` and without a co-author (see the assumptions in proposal.md); verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`, which adds its requirements to `openspec/specs/server/spec.md`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-server-start-failures`.
