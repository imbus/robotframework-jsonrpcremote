# Tasks

## 1. Peer: no finalizer

- [ ] 1.1 In `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py`, remove the `weakref.finalize` call from `JsonRpcPeer.__init__`, the method `_on_finalize` and the `weakref` import (design decision 1). Verify with new tests in `tests/test_peer.py`, each holding the peer only in a local variable, taking a `weakref.ref`, dropping the variable and calling `gc.collect()`; run them against the unchanged peer first and see them fail:
  - a started peer that was stopped is freed;
  - a started peer whose connection the remote side closed is freed once its completion has resolved;
  - a peer with an attached endpoint that answered a request is freed together with the endpoint once the connection has closed

## 2. Peer: `stop()` when the read loop never ran

- [ ] 2.1 Move the body of the `finally` in `io_loop()` into one cleanup method, call it there, and call it from `stop()` after the read task and the handlers are cancelled when the cleanup has not run yet (design decision 2). Verify with new tests in `tests/test_peer.py`, using `_FakeWriter` where writes or closing are checked; run them against the unchanged peer first and see them fail:
  - a peer that was never started: `stop()` returns and `completion` has the result `True`;
  - a peer stopped right after `start()`: call `stop()` in the same task and bound the wait with `asyncio.timeout(2)`; `stop()` returns and `completion` has the result `True`;
  - a request sent on a peer that was never started fails with `JsonRpcConnectionClosedError` without a cause when the peer is stopped;
  - after `stop()` on a peer that was never started, a new request fails immediately and nothing is written;
  - stopped before its read loop ran, a peer closes its writer with `auto_close=True` and leaves it open with `auto_close=False`
- [ ] 2.2 In the cleanup method, wait for the writer to close through `asyncio.shield()`, with a done callback that retrieves the result of the shielded wait and does not reference the peer (design decision 3). Verify with new tests in `tests/test_peer.py` that use a writer stand-in whose `wait_closed()` awaits one future shared by all callers; run them against the unchanged peer first and see the first one fail:
  - the remote side closes the connection, the peer waits for the close, a second task waits for the same close, and the peer is stopped: the second wait is not cancelled and ends normally once the shared future is resolved;
  - `stop()` returns while the shared future is still open;
  - a peer stopped before its read loop ran returns from `stop()` while the shared future is still open, and its writer has been closed;
  - when the shared future then fails, asyncio reports no exception that was never retrieved, checked through the loop's exception handler
- [ ] 2.3 Add a section "Lifecycle" under "Advanced Topics" in `packages/jsonrpcpeer/README.md`: `start()` and `run()`, what `completion` reports, that `stop()` ends the peer at any time, also before or right after `start()`, and returns without waiting for the writer to close, what `auto_close` closes, and that a peer that has ended is freed once nothing references it. Verify that each statement matches the tests of 1.1, 2.1 and 2.2

## 3. Peer: construction outside a running event loop

- [ ] 3.1 Create the completion future on first use with `asyncio.get_running_loop().create_future()`, through one private helper that `completion`, `io_loop()` and the cleanup method use (design decision 4). Verify with a synchronous test in `tests/test_peer.py`: it creates two connected stream pairs in a new event loop, creates the peers while no loop runs with warnings turned into errors, then runs a request between them in that loop, stops both peers and closes the server and the loop without a `ResourceWarning`. Run it against the unchanged peer first and see it fail with the deprecation warning on 3.12; 5.2 checks the `RuntimeError` on 3.14
- [ ] 3.2 Add to the "Lifecycle" section of `packages/jsonrpcpeer/README.md` that a peer can be created before an event loop runs and binds to the loop that runs when it is first used. Verify that the statement matches the test of 3.1

## 4. Client and server release their peers

- [ ] 4.1 Add a test to `tests/test_server_stdio.py` that runs `run_stdio_server` over the existing loopback fixture, takes a `weakref.ref` to the peer that `handle_client` registered in `server_main._clients` after the client's initialize request, lets the client disconnect, awaits the server task and calls `gc.collect()`. Verify that the reference is dead, and that the test fails when the finalizer line is put back temporarily
- [ ] 4.2 Add a test to `tests/test_client_session.py` that takes a `weakref.ref` to the peer of a running session, ends the session, drops the session and calls `gc.collect()`. Verify that the reference is dead, and that the test fails when the finalizer line is put back temporarily

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 5.2 Run the unit tests on Python 3.14 and 3.15, each in its own environment outside the repository (`UV_PROJECT_ENVIRONMENT=<dir>/venv-<version> uv sync --frozen --all-extras --all-packages --dev --python <version>`, then `<venv>/bin/python -m pytest`, not `uv run`). Verify that all pass, that the test of 3.1 fails on 3.14 against the unchanged `peer.py`, and that five runs on 3.15 with `-W error::pytest.PytestUnhandledThreadExceptionWarning` pass
- [ ] 5.3 Run `uv run --all-packages robotcode run`; verify all Robot suites pass. This change adds no Robot test: whether a peer is freed, how `stop()` ends a peer whose read loop never ran, and creating a peer without a running loop cannot be observed from Robot Framework, and the cancelled close depends on timing, so a Robot test for it would pass or fail by chance; the unit tests of 1.1 to 4.2 cover every scenario
- [ ] 5.4 Repeat the leak measurement from the review: start `robot-jsonrpcremote-server JsonRpcRemote.Echo` on a free port, open 1200 connections in a row (connect, import the library, stop), and read the server's RSS before and after from `/proc/<pid>/status`; once with the unchanged `peer.py` and once with the fix, with a script in the scratchpad. Verify that the growth with the fix is in the range the review measured with the finalizer neutralized (about 2 MiB, against about 12 MiB without the fix)
- [ ] 5.5 Commit code, tests, README, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`): subject `fix(peer): free ended peers and end peers stopped before they ran`, a body that explains the finalizer leak with the numbers from 5.4, the `stop()` hang before and right after `start()`, the cancelled close that the client's worker thread printed, and the construction outside a running loop, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`, which adds its requirements to `openspec/specs/jsonrpc-peer/spec.md`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-peer-lifecycle`, then run `uv run ruff format --check .`.
- Set PEER-4, PEER-6 (without the `get_event_loop` point) and the peer part of PEER-7 to done in `playground/anforderungen-und-ideen.md`.
