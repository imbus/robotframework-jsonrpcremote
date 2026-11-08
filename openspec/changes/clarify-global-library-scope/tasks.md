# Tasks

Every new test that covers a change is run against a copy of the client package without that part of the change, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the server processes that the tests start. Tests that pin behavior that stays, those of group 1, pass before and after; their task names the copies of the server or of a test library that make them fail. A copy of a library in `atests/` takes effect when the suite runs from a copy of `atests/`.

## 1. A GLOBAL library on the server

- [ ] 1.1 Add the test libraries in `atests/`:
  - `GlobalCounterLib.py`: a class with `ROBOT_LIBRARY_SCOPE = "GLOBAL"`; a keyword `count(caller="")`, which returns how often the instance was called; a keyword `end_server_process()`, which ends the server process with exit code 3, named so that it does not clash with `Exit Server` of `ConnectionLossLib` in the stdio suite; and a listener of its own (`ROBOT_LIBRARY_LISTENER`, API version 3), which writes a line with the name and the arguments of each `start_keyword`, and a line `close`, to the file that the environment variable `GLOBAL_COUNTER_EVENTS` names, and nothing without the variable;
  - `SuiteCounterLib.py` and `TestCounterLib.py`: the same `count`, with `ROBOT_LIBRARY_SCOPE = "SUITE"` and `"TEST"`, without the listener and `end_server_process()`.
- [ ] 1.2 Add `atests/global_library.robot` (design decision 3). Its suite setup removes the events file in `${TEMPDIR}`, sets `GLOBAL_COUNTER_EVENTS` to it, and starts a server of its own on port 8287 through `IsolatedServerControl`, with the three libraries; the suite teardown stops it. These tests, in this order:
  - `First Session`, `Second Session` and `Third Session`, from one template: each imports the three libraries with `rpc_scope=TEST` under aliases of its own and calls `Count` of each; the `GLOBAL` library returns 1, 2 and 3, the other two 1 each time;
  - `A Client That Ends Its Session Leaves The Global Library To Another`: client B imports `GlobalCounterLib` with `rpc_scope=SUITE`, and client A with `rpc_scope=TEST`; A calls `Count    a`;
  - `The Other Client Still Has The Instance And The Listener`: B's `Count    b` returns the count after A's, and the events file has a `start_keyword` line with `b` and no line `close`;
  - `The Server Closes The Listener Of A Global Library Once When It Stops`, with the tag `posix`: the events file has no line `close`; after `Stop Jsonrpc Server`, it has exactly one; the test then starts the server again.

  Verify the failures in these copies:
  - the second and the third session test, with `ROBOT_LIBRARY_SCOPE = "SUITE"` in `GlobalCounterLib`, and with `"GLOBAL"` in each of the other two libraries; the first session counts 1 with every scope;
  - the test of the other client, in a copy of the server whose `_robot_finalize_library()` also calls `scope_manager.unregister_listeners()` for every other library in the keyword store, and, for its count, with `ROBOT_LIBRARY_SCOPE = "SUITE"` in `GlobalCounterLib`;
  - the test of the close, in a copy of the server that replaces `IMPORTER.close_global_library_listeners` of Robot Framework's `robot.running.namespace` with a function that does nothing, and in a copy whose `_robot_finalize_library()` calls `scope_manager.unregister_listeners(close=True)`, which closes the listener before the stop.

## 2. The reconnect warning by scope and transport

- [ ] 2.1 In `src/JsonRpcRemote/__init__.py`, pick the end of the reconnect warning by the scheme of the URI and the `scope` of the registered library definition (design decision 1). Give `tests/fake_server.py` an attribute `library_scope`, which sets `LibraryDefinition.scope` in its answer to an import. In `tests/test_client_connect_retry.py`, add `test_reconnect_warning_for_a_global_library_says_its_state_is_kept`, like `test_call_after_a_lost_connection_reconnects_and_logs_a_warning`, but with `server.library_scope = "GLOBAL"`: the warning ends with the new text and does not contain `was reset`. The existing test keeps the old text for a library without a scope. Verify that the new test fails in a copy with one text for every scope.
- [ ] 2.2 At the end of `atests/global_library.robot`, add `A Reconnect To A Global Library Over TCP Says Its State Is Kept Unless The Server Restarted`, with `LogCapture.py`: it imports `GlobalCounterLib` with `rpc_scope=TEST` and connect retry, calls `Count`, restarts the server and calls `Count` again, which returns 1, since the restarted server has a new instance; the captured warning ends with the new text. Verify that the test fails in the copy of 2.1.
- [ ] 2.3 In `atests/stdio_vars.py`, add the command of our server for `GlobalCounterLib`. In `atests/stdio_connect_retry.robot`, import it with connect retry under an alias of its own, and add `A Reconnect To A Global Library Over Stdio Says Its State Was Reset`: `Count` returns 1, `End Server Process` fails with the lost connection, the next `Count` returns 1 again, and the captured warning for that URI ends with `so its server-side state was reset.` The existing test of the suite keeps matching its own warning. Verify that the new test fails in a copy that picks the text by the scope alone.
- [ ] 2.4 In `docs/src/content/docs/guides/lost-connections.mdx`, section Reconnecting after a lost connection: after the quoted warning, give the end that it has instead for a library with the scope `GLOBAL` over TCP; in the paragraph after it, say that over stdio the new session has a new server process, so nothing of the earlier instance is left, whatever its scope. Verify the page against the behavior of 2.1 to 2.3.

## 3. Integration checks

- [ ] 3.1 Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy`, and verify that they pass.
- [ ] 3.2 Run `uv run --all-packages pytest` and `uv run --all-packages robotcode run`, and verify that all unit tests and all Robot suites pass.
- [ ] 3.3 Run `npm run build` in `docs/` and verify that the site builds without broken links.

## Workflow follow-up

- Commit the plan as `docs(openspec): plan clarify-global-library-scope`.
- After the implementation, check CI, including the Windows and the minimum Robot Framework jobs, then archive the change.
