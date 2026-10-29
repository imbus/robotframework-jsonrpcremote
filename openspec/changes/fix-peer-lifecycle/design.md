# Design

## Context

See proposal.md for the motivation and specs/ for the requirements.

**How a peer lives today** (`packages/jsonrpcpeer/src/jsonrpcpeer/peer.py`):

- `__init__` creates the completion future with `asyncio.Future()` and registers `weakref.finalize(self, self._on_finalize)`. `_on_finalize` cancels the read task if the peer is still running.
- `start()` sets `running` and creates the read task for `io_loop()`.
- The `finally` of `io_loop()` is the only cleanup. It clears `running`, marks the connection closed and fails waiting requests (`_mark_closed`), resolves the completion future unless an error already set it, and with `auto_close` closes the writer and waits for it to close.
- `stop()` clears `running`, cancels and awaits the read task if it is not done, cancels the handler tasks in flight, and then awaits the completion future.

**Why `stop()` hangs when the read loop never ran:** without a read task, nothing ever resolves the completion future. A task that is cancelled before its first step never enters its coroutine, so the `finally` of `io_loop()` does not run either. This holds on every Python version.

**Why stopping can cancel the client's close:** `StreamWriter.wait_closed()` awaits one close future that the writer's protocol shares among all callers. Cancelling a task cancels the future it waits for, so when `stop()` cancels the read task while its cleanup waits in `wait_closed()`, every other caller waiting for that close gets a `CancelledError`. The client is one of them: `close_connection()` waits for the same writer when its session ends.

**Who creates peers:** the client in `_Session._start_peer` and the server in `handle_client`, both inside a running loop and followed directly by `start()`; `completion` is only read after that. The package examples do the same.

## Goals / Non-Goals

**Goals:**

- One cleanup that runs exactly once per peer, whether the read loop ends or `stop()` ends a peer whose read loop never ran.
- No object of the peer that refers back to it from outside its own reference graph.
- Stopping never cancels a wait that does not belong to the peer.

**Non-Goals:**

- Restarting a peer: `start()` after `stop()` or after the connection closed stays unsupported, as today.
- `asyncio.Future()` in `send_request_typed`: it always runs inside a coroutine, so a running loop exists.

## Decisions

### 1. Remove the finalizer instead of making it self-free

`__init__` no longer registers a finalizer; `_on_finalize` and the `weakref` import go away.

- **Alternative:** a finalizer that does not reference the peer, for example one that cancels the read task. It can never fire while it would matter: as long as the read loop runs, the read task references the peer through `io_loop`, so the peer cannot be collected. After the loop ended there is nothing left to cancel.
- The probe confirmed that without the finalizer a stopped peer, a peer whose connection the remote side closed, and a peer with an attached endpoint that answered a request are all collected by `gc.collect()`. The endpoint and the peer reference each other, so freeing them needs the cyclic garbage collector; the requirement asks for no more.

### 2. One cleanup method shared by the read loop and `stop()`

The body of the `finally` in `io_loop()` moves into one method, for example `_finish(close_error)`. `io_loop()` calls it in its `finally`, unchanged in effect. `stop()` calls it after it has cancelled the read task and the handlers, when the cleanup has not run yet, which `_closed` tells. That covers the peer that was never started and the read task that was cancelled before its first step. `stop()` then awaits the completion future as before, which has resolved by then.

- **Alternative:** a flag that `io_loop()` sets when it starts, so `stop()` would not cancel a read task that has not run yet but wait for it. The task would then start reading and block until data arrives.
- **Alternative:** let `stop()` only return when the read loop never ran, without ending the peer. Rejected in review: the peer would stay half alive, with `completion` open and waiting requests never failing, unlike every other way a peer ends.
- With `auto_close`, `_finish` closes the writer, as at the end of the read loop. The writer then belongs to the peer from construction on, as `auto_close` already says.

### 3. The cleanup waits for the writer's close shielded

The cleanup method waits for the writer to close through `asyncio.shield()`. When `stop()` cancels the read task during that wait, only the read task's own wait ends; the shared close future and every other caller's wait go on. `stop()` returns without waiting for the close, as it does today. A done callback on the shielded wait retrieves its exception, so a writer whose `wait_closed()` raises, like the stdio pipe, leaves nothing that asyncio reports as never retrieved. The callback does not reference the peer, so it does not keep the peer alive.

- **Alternative:** `stop()` does not cancel a read task that is already in its cleanup but waits for it. A close that takes long, for example with a full send buffer towards a remote side that no longer reads, would then hold up `stop()` as well.
- **Alternative:** only make the client tolerate the `CancelledError`. Every other user of the writer would still be hit; the client's defense follows in `fix-client-session-end` in addition, not instead.

### 4. The completion future is created on first use, from the running loop

`__init__` stores no future. A private helper creates it with `asyncio.get_running_loop().create_future()` on first use and returns the same future after that. `completion`, `io_loop()` and `_finish` use the helper.

- **Alternative:** create the future in `start()`. `completion` and `stop()` can come before `start()`, so they would need the same lazy creation anyway.
- **Alternative:** keep `asyncio.Future()` in `__init__` and silence the warning. It still fails on Python 3.14 and later.

### 5. Tests prove collection at three levels and run on the Python versions where the defects show

- **Peer** (`tests/unit/test_peer.py`): the scenarios of the delta spec. For collection, each test keeps the peer only in a local variable, takes a `weakref.ref`, drops the variable, runs `gc.collect()` and asserts that the reference is dead. The construction test is a synchronous test: it creates the peers while no loop runs, with warnings turned into errors, and then runs a request in a new loop.
- **Server** (`tests/unit/test_server_stdio.py`): over the existing loopback fixture and `run_stdio_server`, the peer that `handle_client` created for the connection is collected after the client disconnected. `handle_client` serves TCP connections too, so this covers the leak measured on the server.
- **Client** (`tests/unit/test_client_session.py`): the peer of a session is collected after the session ended.
- **Shared close:** a writer stand-in whose `wait_closed()` awaits one future shared by all callers, as `StreamWriter` does, makes the cancelled close deterministic: the test stops the peer while it waits there and checks a second waiter. The real race only shows in some runs of the full suite.
- **Python versions:** the project environment and CI run 3.12, where the construction test fails before the fix with the deprecation warning turned into an error; from 3.14 on it fails with a `RuntimeError` instead. Until `add-ci-version-matrix`, the unit tests therefore also run locally on 3.14, and on 3.15, where the cancelled close showed most often.
- **Leak measurement:** 1200 connections in a row against a local server, before and after the fix. It is a check for this change, not a committed test.

## Risks / Trade-offs

- **[Reading `completion` without a running loop now raises `RuntimeError`]** Before, Python 3.12 and 3.13 returned, with a deprecation warning, a future bound to the thread's default loop. → Such a future could only be awaited in that loop; the client, the server and the examples read `completion` only inside a running loop. The README says that the peer binds to the loop on first use.
- **[`stop()` closes a writer that the caller passed in, although the peer never ran]** → Only with `auto_close`, the default, which already closes the writer whenever the peer ends; `auto_close=False` leaves it open.
- **[The writer's close goes on after `stop()` returned]** → Intended: the close belongs to the writer, which the peer closes with `auto_close` anyway, and the shielded wait holds no reference to the peer.
- **[Collection tests depend on the garbage collector]** → The tests hold no other references and call `gc.collect()` explicitly; the probe gave the same result on every run and Python version.
- **[An unretrieved exception in the completion future]** When the read loop fails, the future holds the error. If nobody awaits `completion`, asyncio logs it when the future is collected, which now happens instead of never. → Both the client and the server await `completion` through `run()` or directly; the peer tests read it.
