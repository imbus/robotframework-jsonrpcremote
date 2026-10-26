# Tasks

## 1. Submission point

- [ ] 1.1 Add `_Session.submit(coro)` with a lock, an `ended` event and a set of outstanding calls whose done-callback removes entries under the same lock (design decision 1); verify with a test: submitting to a session that has not started, or has ended, raises a `ConnectionError` whose message ends in "is closed", and no "coroutine … was never awaited" `RuntimeWarning` is emitted
- [ ] 1.2 Make `_run` set `ended` and fail the outstanding calls with `ConnectionError` outside the lock when the worker ends (design decision 2); verify with a test: a call submitted to an event loop that never runs it (an idle loop set as the session's loop) fails with `ConnectionError` within 1 second after the worker body ran against a closed port and ended

## 2. Worker thread errors

- [ ] 2.1 Make `_run` catch `Exception` from `asyncio.run(...)` and log it at debug level with traceback through a module logger instead of re-raising (design decision 3); verify with a test that replaces `threading.excepthook` with a recorder: a session started against a closed port ends with `start_error` set, the recorder is never called, and `caplog` holds the debug record

## 3. Keyword calls

- [ ] 3.1 Make `JsonRpcRemote.run_keyword` read the session once and submit through `submit()` (design decision 4); verify with a fake-server test: after the fake server closes the connection and the session's worker has ended, a keyword call fails with `ConnectionError` "… is closed" instead of `RuntimeError: Event loop is not initialized yet`, and the existing keyword round-trip tests still pass

## 4. Teardown

- [ ] 4.1 Make `_finalize_session` suppress the errors of every step, keep every step bounded by `timeout`, and always run the `stdio` process backstop and the resource cleanup, also when `peer` or `loop` is `None` (design decision 5); verify with tests: with an event loop that never processes scheduled work and `timeout=0.5`, it returns within 2 seconds without raising and clears the resources; with a closed loop it returns without raising; with a recorded process (a `MagicMock` with `returncode=None`) and no peer, the process is killed

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 5.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass and no "Exception in thread" output appears in the console log
- [ ] 5.3 Commit code, tests and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `fix(client): never hang or raise when a session ends`, a body that explains the three gaps, `Refs #2`, and the trailer `Co-authored-by: Fabian Tsirogiannis <fabian.tsirogiannis@imbus.de>`; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive` after `fix-client-handshake-cleanup` is archived.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-client-stranded-calls`.
