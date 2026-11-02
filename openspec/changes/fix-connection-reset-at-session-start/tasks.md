# Tasks

Every new test is run once against the code without the part of the change it covers, and must fail there.

## 1. Client: a reset while a session starts

- [x] 1.1 In `tests/fake_server.py`, add the scripted answer `RESET_CONNECTION`: the handler aborts the connection of the request with a TCP reset and gives no answer, using the code that `close_connections(reset=True)` uses (design decision 4). It is verified by the tests of 1.2, which fail if the client sees a clean close instead.
- [x] 1.2 In `_Session._run_client`, run the cleanup of a failed start after the `except` block, with the comment from design decision 1. Verify with new tests:
  - `tests/test_client_session.py`: with `RESET_CONNECTION` for `INITIALIZE_REQUEST`, the call fails with a `JsonRpcConnectionClosedError` whose cause is a `ConnectionResetError`, following `__cause__` and `__context__` comes to an end, and the next call connects and returns its result. This covers the client scenario The error chain has an end.
  - `tests/test_client_connect_retry.py`: with `RESET_CONNECTION` for every attempt within a short window, the call fails with `Could not connect to … within …`, and its chain comes to an end. This covers the client scenario Every attempt of connect retry is reset.
- [x] 1.3 Robot tests (design decision 4), which fail against the code without 1.2 with exit code 255 of the nested run, while the outer run goes on:
  - **The new library `atests/ResetServer.py`** with the keywords `Start Reset Server` and `Stop Reset Server`.
  - **The new suite `atests/connection_reset.robot`** on port 8282.
  - **Reset during the import:** it starts the reset server and runs `atests/_nested/failing_import.robot` nested, with its documentation updated for the second user. It checks that the only execution error names `JsonRpcConnectionClosedError: Connection closed before a response was received`, and that the test of the nested suite passed, which also shows that the output file is complete. This covers the client scenario Reset during the library import.
  - **Reset when a later session starts:** the new `atests/_nested/reset_at_session_start.robot` has a first test whose session with `rpc_scope=TEST` works against the real server, a second test that replaces it with the reset server and expects the error with `Run Keyword And Expect Error`, and a third test that starts the real server again and whose `Echo` returns its result. The outer test checks that all three passed. This covers the client scenario Reset when a later session starts.

## 2. Peer: the error of the completion

- [x] 2.1 In `peer.py`, rename `_closing_done` to `_retrieve_exception` and add it to the completion future in `_completion()` (design decision 2). Verify with new tests:
  - `tests/test_peer.py`: when reading fails and nobody waits for the completion, `gc.collect()` brings no `never retrieved` report, checked as in `test_close_while_sending_reports_the_closed_connection`; a later `await peer.completion` raises the error. This covers both peer scenarios.
  - `tests/test_client_session.py`: after a start that was reset, with the session dropped and `gc.collect()`, the logger `asyncio` has no `never retrieved` record. This covers the client scenario Asyncio reports nothing. It adds no Robot test, because Robot Framework does not show that report in a result of the run.

## 3. Test helper: stopping the server

- [x] 3.1 In `atests/ServerControl.py`, make `stop_jsonrpc_server`, `kill_jsonrpc_server` and `wait_for_jsonrpc_server_to_exit` return only when the port no longer accepts connections (design decision 3). Verify:
  - The new `tests/test_server_control.py`: with a process that has ended and a listening socket that closes 0.3 seconds later, each keyword returns only after that, and a port that stays open raises after the time limit, which the test shortens.
  - On Windows with a venv: 30 connections right after `stop_jsonrpc_server` are all refused (before this change, about 25 of 30 were accepted).
  - It adds no Robot test: `atests/session_start.robot` already expects the refused connection right after the stop.

## 4. Documentation

- [x] 4.1 Review `docs/src/content/docs/guides/lost-connections.mdx` and `docs/src/content/docs/roadmap.mdx` against the implementation. Verify that no page describes this failure differently; the change adds no page text and no example, because a failed start now behaves as the pages describe failed starts.

## 5. Integration checks

- [x] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 5.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"`; verify all Robot suites pass
- [x] 5.3 On Windows, run the unit tests and the Robot suites; verify all pass, `atests/connection_reset.robot` included
- [x] 5.4 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`):
  - **Subject:** `fix: fail only the call when a connection reset hits a session start`.
  - **Body:** explains the cycle between the start error and the reset, why it ended the whole run, the report of the unretrieved exception, and the wait for the closed port in the test helper.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive` and sync its delta specs into `openspec/specs/client` and `openspec/specs/jsonrpc-peer`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-connection-reset-at-session-start`.
- In `playground/anforderungen-und-ideen.md`, set CLIENT-7 to done and add CLIENT-14 as done. Add CLIENT-15 as open: a session that failed to start stays in memory until the process ends, after a reset as after a rejected handshake.
- Decide whether to report the missing cycle check in `robot/utils/error.py` to Robot Framework.
