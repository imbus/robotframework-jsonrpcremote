# Tasks

Every new or changed test that covers a part of the change is run against a copy of the package without that part, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the server processes that the Robot tests start.

## 1. The code `SHUTTING_DOWN` for a stopping server

- [x] 1.1 In `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py`, add `SHUTTING_DOWN = -32002` to `RobotJsonRpcErrorCode`. In `packages/server/src/robot_jsonrpcremote_server/_runner.py`, let `_shutting_down()` answer with it; the message stays `server is shutting down`. Tests:
  - `tests/server/test_runner.py`: `test_submission_after_stop_fails_at_once` and `test_stop_completes_the_running_command_and_fails_the_queued_one` expect `^RPC Error -32002: server is shutting down$`. This covers a keyword call and a library import after the stop began, and a finalize.
  - `tests/server/test_endpoint.py`: `test_error_of_a_stopping_server_leaves_run_keyword` expects `RobotJsonRpcErrorCode.SHUTTING_DOWN`.
  - `tests/protocol/test_protocol.py`: `test_error_codes_of_the_protocol`, which pins every code of the protocol, includes `SHUTTING_DOWN`.

  These cover the three scenarios of the server requirement "Requests that can no longer run are rejected". Verify that they fail in a copy of the server whose `_shutting_down()` still answers with `-32603`. No Robot test: the message that Robot Framework shows stays the same, and the time between the start of a stop and the closed listener is too short to reach reliably from a suite (design, Tests).
- [x] 1.2 In `docs/src/content/docs/reference/protocol.mdx`, add the row `-32002` `RobotJsonRpcErrorCode.SHUTTING_DOWN` for a library import, a keyword call or a finalize while the server is stopping, and take the stopping server out of the row `-32603`. In `docs/src/content/docs/reference/server.mdx`, in the steps of a stop, name the code of `server is shutting down`. Verify both pages against 1.1.

## 2. Connect retry repeats only connection failures

- [x] 2.1 In `_connect_with_retry` of `src/JsonRpcRemote/__init__.py`, raise every failure that is neither an `OSError` nor a `JsonRpcResponseError` with the code `SHUTTING_DOWN` at once, before it begins an outage or counts as an attempt (design, first decision). Add these tests to `tests/client/test_client_connect_retry.py`, with the fake server and a window of 10 seconds where retry is on:
  - `test_refused_import_fails_at_once_with_connect_retry`, parametrized over `-32602` with `Library 'FakeLib' is not available.` and `-32603` with the error of a library that fails to import: the import fails with the `RemoteError` of the message, after a single import and within 5 seconds. This covers the scenarios "Server does not serve the library" and "Library fails to import on the server".
  - `test_import_answered_with_shutting_down_is_tried_again`: the first import is answered with `-32002`, and the import succeeds after the second. This covers "Server is stopping during the library import".
  - `test_shutting_down_without_connect_retry_fails_at_once`: the import fails with the `RemoteError` `server is shutting down` after a single import. This covers "Stopping server without connect retry".
  - `test_uri_that_the_client_cannot_use_fails_at_once_with_connect_retry`: `htp://127.0.0.1:8271` fails with the `ValueError` that names `htp`, within 5 seconds. This covers "URI that the client cannot use".
  - `test_refused_import_when_a_lost_session_is_replaced_fails_the_call_at_once`: after a lost connection, the import of the next call is refused, and the call fails at once with the message. This covers "Refused import when a lost session is replaced".
  - `test_refused_import_does_not_count_as_a_failed_attempt`: the server is down for a few attempts and then refuses the import once. The next call connects, and the INFO message `Connected to … after …` counts only the failed connections and the successful one.

  The existing tests of the requirement "With connect retry every connection attempt is repeated within the window" cover its two scenarios unchanged. Existing tests that stood in for a server that is not ready yet with an error response to the import now use a reset connection: `test_failed_attempts_are_repeated_every_interval`, `test_connection_that_needed_several_attempts_is_logged_as_info` and `test_reconnect_warning_counts_the_failed_attempts`. In `tests/client/test_client_failures.py`, the test of the last error that is named when connect retry gives up uses the answer of a stopping server, the only error response that is repeated; it becomes `test_answer_of_a_stopping_server_is_named_as_the_last_error_when_connect_retry_gives_up`. Verify the failures in these copies of the client:
  - the tests of the refused imports, of the URI, of the replaced session and of the attempts fail in a copy that repeats every failure, as today;
  - the test of `-32002` with retry and the test of the last error fail in a copy that repeats only `OSError`;
  - the test without retry passes before and after; it fails in a copy that repeats `-32002` even without connect retry;
  - the test of the attempts fails in a copy that checks the failure only after it has counted it.
- [x] 2.2 In `atests/connection/connect_retry.robot`, let the suite's server also serve `MissingDependencyLib`, with one variable for the libraries of every start of the server. Add the tests:
  - `A Refused Import Fails At Once Despite Connect Retry`: `Import Library` of `OtherLibrary` with `rpc_connect_retry_timeout=10s` fails with `*Library 'OtherLibrary' is not available.` within 5 seconds.
  - `A Library That Fails To Import Fails At Once Despite Connect Retry`: `Import Library` of `MissingDependencyLib` with `rpc_connect_retry_timeout=10s` fails with an error that holds `No module named 'a_module_that_does_not_exist'` within 5 seconds.

  These cover the scenarios "Server does not serve the library" and "Library fails to import on the server" from Robot Framework. Verify that both fail in the copy of 2.1 that repeats every failure, and run the suite once with `--randomize tests`.
- [x] 2.3 In `docs/src/content/docs/guides/lost-connections.mdx`, section Connect retry, say which failures are repeated:
  - a server that cannot be reached or that is stopping;
  - not a server that answers that the import cannot succeed, such as `Library 'OtherLibrary' is not available.` or the error of a library that fails to import;
  - not a URI that the client cannot use.

  The latter two fail at once, as without connect retry. Verify the page against 2.1 and 2.2. The example `docs/examples/connect-retry` shows a server that is still starting and stays as it is. The guide Failures of remote keywords keeps its messages, which do not change. The page Status and roadmap already lists connect retry as available, so it stays unchanged.

## 3. Integration checks

- [x] 3.1 Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy`, and verify that they pass.
- [x] 3.2 Run `uv run --all-packages pytest` and `uv run --all-packages robotcode run`, and verify that all unit tests, the examples of the documentation site and all Robot suites pass.
- [x] 3.3 Run `npm run build` in `docs/` and verify that the site builds without broken links.

## Workflow follow-up

- Commit the plan as `docs(openspec): plan fix-connect-retry-rejected-imports`, and the implementation as one signed commit.
- After Daniel's push, check CI and the Docs workflow, including the Windows and the minimum Robot Framework jobs, then archive the change with `/opsx:archive` and commit the archive as `docs(openspec): archive fix-connect-retry-rejected-imports`.
- Mark CLIENT-11 as done in `playground/anforderungen-und-ideen.md`.
