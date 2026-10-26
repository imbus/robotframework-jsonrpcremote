# Tasks

## 1. Connection-closed error type

- [x] 1.1 Add `JsonRpcConnectionClosedError(ConnectionError)` to `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py` next to the other peer exceptions and re-export it from `jsonrpcpeer/__init__.py` in the existing `from .peer import X as X` style; verify with a new unit test in `tests/unit/test_peer.py` that it imports from `jsonrpcpeer` and is a subclass of `ConnectionError`

## 2. Fail outstanding requests when the connection closes

- [x] 2.1 In `io_loop`, remember the exception that ends the loop (the one recorded on `completion`), and in its `finally`, before any `await`: set the closed flag, take and clear the pending map, fail each pending future that is not done yet with its own `JsonRpcConnectionClosedError` (`__cause__` = remembered exception, if any), then set `completion` (design decisions 1, 2, 5); verify with a `peer_pair` test: a request waits for a handler that never answers, the remote side closes its writer, the request fails with `JsonRpcConnectionClosedError` without a cause, and the pending map is empty
- [x] 2.2 Add tests for the remaining clean closures and verify they pass: local `stop()` fails a waiting request without a cause; several waiting requests all fail; with `request_timeout=5`, a waiting request fails with `JsonRpcConnectionClosedError` within 1s of the close instead of timing out
- [x] 2.3 Add tests for closures by error and verify they pass: `reader.set_exception(ConnectionResetError(...))` fails a waiting request with that error as `__cause__`; a frame truncated by EOF fails it with the `IncompleteReadError` as cause; an incoming message above `max_message_size` fails it without a cause

## 3. Reject requests after the close

- [x] 3.1 Check the closed flag at the top of `send_request_typed`, before allocating an id, creating a future or writing (design decision 4); verify with a test on a peer whose reader is already at EOF (`auto_close=False`, `MagicMock` writer, peer run to completion): `send_request("ping")` raises `JsonRpcConnectionClosedError` whose message names `'ping'`, and `writer.write` is never called
- [x] 3.2 Add a paragraph to the "Error Handling" section of `packages/jsonrpcpeer/README.md`: outstanding and new requests fail with `JsonRpcConnectionClosedError` (a `ConnectionError`) once the connection closes, with the read error as cause where there is one; verify the section reads correctly in the rendered README

## 4. Race between sending and closing

- [x] 4.1 In `send_request_typed`, if writing the request raises and its future has already been failed by the closure, raise that future's `JsonRpcConnectionClosedError` (which also marks it retrieved); otherwise let the write error propagate (design decision 6); verify with a test using a writer whose `drain()` yields so the read loop hits EOF and then raises `ConnectionResetError`: the caller gets `JsonRpcConnectionClosedError`, and an exception handler installed on the running loop records no "never retrieved" report after the references are dropped and `gc.collect()` ran
- [x] 4.2 Add a regression test that a write error unrelated to the closure still propagates unchanged: with a small `max_message_size`, `send_request` raises the existing `ValueError` for the oversized outgoing message and the peer is not marked closed; verify it passes

## 5. Integration checks

- [x] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 5.2 Run `uv run --all-packages robotcode run`, since the client's behavior on a dropped connection changes; verify the existing Robot suites still pass
- [x] 5.3 Commit code, tests, README and this `tasks.md` as one signed commit on `main` (`git commit -S`): subject `fix(peer): fail pending requests when the connection closes`, a body that explains the behavior, `Refs #2`, and the trailer `Co-authored-by: Fabian Tsirogiannis <fabian.tsirogiannis@imbus.de>`; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`, which creates `openspec/specs/jsonrpc-peer/spec.md` and moves the change to `openspec/changes/archive/`.
- Commit the archive as its own signed commit: `docs(openspec): archive fix-peer-pending-requests`.
