# Tasks

This change adds tests and changes no code, so there is no part of a change to take out. Instead, each new test is run against a copy of the package with the code it covers broken, as the tasks name it, and must fail there.

It adds no Robot test, because it changes no behavior that Robot Framework could observe, and it changes no documentation, for the same reason. The Robot suites run as a regression check in group 3, and `add-robot-integration-tests` brings the Robot tests for the default library and the allowlist.

A test that reveals a bug is marked with `pytest.mark.xfail(strict=True, reason=...)`, with the reason naming the bug, and the bug goes into the backlog for a change of its own. The probes for this plan on 2026-11-03 found none. The mutation test of 3.1 led to a probe that found SERVER-21: a keyword with `sys.exit()` ends the whole server. It is no regression, so it goes to the backlog without a test here.

## 1. Tests over the protocol

- [x] 1.1 In `tests/test_server_end_to_end.py`, add a method to `_Session` that finalizes the imported library, and a library module with a class per scope (`SUITE`, `TEST`) that is its own listener and logs a message from `_close`, like `atests/CloseLogLib.py`. Add tests, with `server_without_libraries` for the module:
  - `test_finalized_library_is_gone`: a keyword call afterwards is answered with `-32603` and `No library '<token>' found.`;
  - `test_finalizing_an_unknown_token_or_twice_is_no_error`;
  - `test_finalizing_closes_the_listener_of_a_library`, parametrized over both scopes: the client gets the message of `_close` while it finalizes.

  Verify that they fail in a copy without `store.libraries.pop` (first test), with the condition `if lib is None` negated (third), and without `scope_manager.end_suite()` (third). The second fails if `_robot_finalize_library` raises for an unknown token.
- [x] 1.2 In `tests/test_server_end_to_end.py`, let `_Session.import_library` return the result, and add a library with a documented, tagged keyword `def full_signature(self, first: str, /, second: int = 5, *rest: str, named: bool = True, plain=None, nested=[1, {"a": 2}], **others: int)`, with the attributes `ROBOT_LIBRARY_VERSION` and `ROBOT_LIBRARY_DOC_FORMAT`. Add tests:
  - `test_library_definition_describes_the_library`: `doc`, `doc_format`, `scope`, `version`, and that `source` names the file and `lineno` is a number;
  - `test_library_definition_describes_a_keyword`: `name`, `doc`, `tags`, and that `source` names the file and `lineno` is a number;
  - `test_library_definition_describes_the_arguments`: for each argument `name`, `type`, `has_default`, `default` and `kind`, including the marker `/` as `POSITIONAL_ONLY_MARKER`, the type `""` of an argument without a type, the default `None` of `plain`, and the default of `nested` read back with `jsonable_to_value`.

  Verify that they fail in a copy without `result.append` in `to_arg_def`, with `is not NOT_SET` swapped in either of the lines of `has_default` and `default`, and without the fields in `to_kw_def`. `required` stays out, because the protocol page calls it reserved.
- [x] 1.3 In `tests/test_server_end_to_end.py`, add a second small library and a fixture for a server with the libraries `SecondLib` and `EndToEndLib`, in this order, and let `_Session.initialize` return the result. Add tests:
  - `test_import_without_a_name_takes_the_first_library_of_the_server`: the definition holds the keyword of `SecondLib`;
  - `test_initialize_reports_what_the_server_serves`: `support_exit` is `True`, `libraries` is `["SecondLib", "EndToEndLib"]`, and `server_info` has the name of the server and its version.

  Verify that they fail in a copy with `self.libraries[1]` (first test) and with `support_exit=False` (second).

- [x] 1.4 In `tests/test_server_end_to_end.py`, let `_Session` keep the params of each forwarded message, and add a keyword that logs a warning and a message with HTML. Add `test_forwarded_message_keeps_its_level_and_html_and_is_not_for_the_console`. The mutation test of 3.1 showed this gap: if the default of `console` in `RobotServerEndpoint.log` flips, each message goes to the client with `console` set. Verify that it fails in a copy with that default flipped, and with `html=html` left out.

## 2. Direct tests, without Robot Framework

- [x] 2.1 In `tests/test_runner.py`, add tests:
  - `test_a_call_from_the_runner_thread_fails`, parametrized over `import_library`, `run_keyword` and `finalize_library`, on a context created in the thread of the test: a `RuntimeError` that names the method;
  - `test_a_command_without_a_robot_context_fails`, parametrized over `_robot_import_library`, `_robot_run_keyword`, `_robot_finalize_library` and `_robot_set_log_level`, called outside a Robot run: a `RuntimeError` with `No execution context available`;
  - `test_a_log_message_while_no_command_runs_reaches_no_subscriber`: after a command of a subscriber has ended, with the fixture `context`, a further message does not reach the subscriber and raises nothing.

  Verify that they fail in a copy without the `raise` of the three methods, without the `raise` of the four functions, without `self._active_subscriber = None` and with `if subscriber is not None` negated.
- [x] 2.2 In `tests/test_endpoint.py`, add tests:
  - `test_robot_log_levels_map_to_the_levels_of_the_protocol`, parametrized: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `CONSOLE`, `HTML`, a level in lower case, and an unknown level, which gives `INFO`;
  - `test_log_messages_for_a_client_that_is_gone_are_not_scheduled`: after `cleanup()`, `log_message` schedules nothing on the event loop of the endpoint, which a `MagicMock` stands in for;
  - `test_handshake_of_a_client_that_is_gone_counts_as_not_done`: after `cleanup()`, a keyword call is answered with `NOT_INITIALIZED`;
  - `test_wait_idle_returns_at_once_before_the_first_request`: `wait_idle(0)` is `True` on a new endpoint;
  - `test_wait_idle_waits_for_the_last_of_two_running_handlers`, with a stub whose keyword calls are released one by one;
  - `test_log_and_exit_without_a_connection_do_nothing`: `log` and `exit` on an endpoint without a peer raise nothing.
  - `test_finalize_all_goes_on_after_a_failure`: with a stub whose finalize fails for the first library, the others are finalized, and no token stays. The coverage of 3.1 showed this gap.

  Verify that they fail in a copy without the `return` for `not self._registered`, without the reset of `initialize_received` and `initialized_received`, without `self._idle.set()` in `__init__`, with `self._idle.set()` in `_request_finished` called for every finished request, and with the checks `if self.rpc_peer` removed. The mapping fails with a level left out of `level_map`. `test_finalize_all_goes_on_after_a_failure` fails without the `except` in `finalize_all`.

## 3. Integration checks

- [x] 3.1 Measure the result in a scratch directory, with `[run] patch = subprocess`, `parallel = True` and `source_pkgs = robot_jsonrpcremote_server` for coverage, and with a mutation test of `_runner.py` and `_endpoint.py` against the unit tests. Verify that `_endpoint.py` has full branch coverage and that `_runner.py` misses only the two branches `if lib is None` and the case without a scope manager. Name in the report of this task every mutant that stays unnoticed, with the reason.
- [x] 3.2 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [x] 3.3 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"` for pytest and Robot; verify all pass.
- [x] 3.4 Run the unit tests on Python 3.13, 3.14 and 3.15 in scratch environments, with `UV_PROJECT_ENVIRONMENT=<scratch>/venv-<version> UV_PYTHON=<version> uv run --all-packages --dev pytest -q`, and restore the environment afterwards with `uv sync --all-extras --all-packages --dev`; verify all pass.
- [x] 3.5 Commit the tests and this `tasks.md` as one signed commit on `main` (`git commit -S`), once Daniel has given the go:
  - **Subject:** `test(tests): cover what can break unnoticed in the server's runner and endpoint`.
  - **Body:** explains that a mutation test showed the gaps, what the new tests cover, and that the fixture of the first plan was dropped because the tests of the real server make it unnecessary.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`. It has no delta specs. Commit the archive as its own signed commit, once Daniel has given the go: `docs(openspec): archive add-server-runner-tests`.
- In `playground/anforderungen-und-ideen.md`, set TEST-5 to done.
