# Tasks

## 1. Release resources when a start fails

- [x] 1.1 In `_Session._run_client`, await `close_connection()` in the start-failure path before `initialized` is set (design decision 1); verify with a fake-server test: `robot/import_library` scripted to fail, the call raises the server's error, and the fake server sees that connection closed within 2 seconds
- [x] 1.2 In `close_connection()`, record the exit code of a released `stdio` server on the session before clearing `_res.process`, waiting briefly after a final `kill()` (design decision 3); verify with a POSIX-only test against the real server (`stdio:` URI with an allowlist that rejects the requested library): when `initialized` is set, `start_error` holds the server's error, the recorded exit code is not `None`, and the process id no longer exists

## 2. Integration checks

- [x] 2.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 2.2 Run `uv run --all-packages robotcode run`; verify all Robot suites still pass, including the `stdio` suites
- [x] 2.3 Commit code, tests and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `fix(client): clean up after a failed handshake`, a body that explains the change, `Refs #2`, and the trailer `Co-authored-by: Fabian Tsirogiannis <fabian.tsirogiannis@imbus.de>`; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive` after `fix-client-session-error-state` is archived, since this delta adds to its `client` spec.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-client-handshake-cleanup`.
