# Tasks

Every new test that covers a change is run against a copy of the packages without that part of the change, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the servers that the tests start. Each task names what it takes out for that check.

The tests of the peer go into a new file `tests/test_typed_endpoints.py`, with a fixture `connected` that gives two started peers on a real connection and small definitions of its own. The connection comes from a new helper `tests/connected_peers.py`, which `tests/test_protocol.py` uses as well. Where a test checks the messages themselves, the other side registers plain handlers with `register_request_handler` and `register_notification_handler`, so that the test does not depend on the definition it checks.

Nothing in this change can be observed from Robot Framework: the messages on the wire stay the same, and so does everything that Robot Framework shows. So no task adds a Robot test, and all Robot suites run as a regression check in group 4.

## 1. Definitions, and answering them

- [x] 1.1 In `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py`, replace `JsonRpcEndpoint` with an abstract class that has the class attribute `rpc_peer: JsonRpcPeer | None = None`, and remove `JsonRpcEndpointProtocol`; export `JsonRpcEndpoint` from `__init__.py` instead (design decision 1). Let `_EchoEndpoint` and `_NotifiedEndpoint` in `tests/test_peer.py` derive from it. Add to `tests/test_typed_endpoints.py`:
  - `test_subclass_that_leaves_out_a_method_cannot_be_created`, checks that the `TypeError` names the method;
  - `test_subclass_with_all_methods_can_be_created`.

  Verify that they pass. Check by leaving out `abc.ABC` and seeing the first test fail.
- [x] 1.2 Add the helper that finds the marks through `__mro__`, and let `attach_endpoint` use it (design decisions 6 and 7). Add to `tests/test_typed_endpoints.py`:
  - `test_override_answers_a_request_with_converted_params`;
  - `test_override_answers_a_notification_with_converted_params`;
  - `test_attached_endpoint_knows_its_peer`;
  - `test_default_implementation_answers`;
  - `test_override_without_an_annotation_gets_the_params_as_they_arrived`;
  - `test_further_subclass_overrides_again`;
  - `test_override_with_a_mark_of_its_own_replaces_the_name`, which also checks `-32601` for the name from the definition;
  - `test_marked_method_without_a_separate_definition`;
  - `test_marked_static_and_class_methods_answer`;
  - `test_attaching_runs_no_property_of_the_endpoint`.

  Verify that they pass, and that `tests/test_peer.py` passes. Check with the old loop over `dir(endpoint)`: the overrides are not found, and the property runs. Check the static and the class method by reading the mark from the member itself instead of its `__func__`.
- [x] 1.3 Add to `tests/test_typed_endpoints.py`, for several endpoints on the receiving side:
  - `test_two_endpoints_on_one_peer`;
  - `test_one_class_implements_two_definitions`;
  - `test_one_method_answers_two_definitions_with_the_same_python_name`;
  - `test_two_handlers_for_one_method_raise`, which checks that the message names the method, and imports the error from the package.

  Verify that they pass. Check by making the helper stop at the first class of the hierarchy: `test_one_class_implements_two_definitions` fails. Check the method for two definitions by making the helper stop at the first mark, and the condition on that by counting every mark, which fails `test_override_with_a_mark_of_its_own_replaces_the_name`.
- [x] 1.4 Let `_call_handler` wait only for a result that is awaitable, and let `THandlerCallable` describe any function (design decision 12). Add to `tests/test_peer.py`:
  - `test_plain_function_answers_a_request_once_with_converted_params`;
  - `test_plain_function_that_takes_the_peer`;
  - `test_plain_function_handles_a_notification_and_reports_nothing`;
  - `test_plain_function_that_raises_is_answered_and_logged`;
  - `test_plain_function_that_raises_a_response_error_keeps_its_fields`;
  - `test_plain_function_that_returns_a_coroutine_is_awaited`.

  Add `test_marked_plain_method_answers` to `tests/test_typed_endpoints.py`, for a request and a notification. Verify that they pass. Check with the old `await` in `_call_handler`, which fails them with `-32603`, and with `inspect.iscoroutinefunction` instead of `inspect.isawaitable`, which fails the test with the coroutine.
- [x] 1.5 Let `send_notification` raise `JsonRpcConnectionClosedError` once the connection has closed (design decision 13), and add `test_notification_after_the_connection_closed_fails_and_is_not_written` to `tests/test_peer.py`. Verify that all tests pass, also those of the client and the server, which call it on a lost connection. Check by removing the test for `_closed`. Update the section on errors in `packages/jsonrpcpeer/README.md`.

## 2. Calling a definition

- [x] 2.1 Add `JsonRpcPeer.remote` with `Callable[..., E]`, the generated subclass with `type` and `functools.cache`, one object for each definition on each peer, and the sending methods that bind their arguments to the signature of the definition (design decisions 2, 4 and 5). Add to `tests/test_typed_endpoints.py`:
  - `test_request_through_remote_sends_its_name_and_params_and_converts_the_result`;
  - `test_params_as_a_keyword_send_the_same_message`, with a definition whose parameter has another name than `params`;
  - `test_request_without_a_return_annotation_returns_the_result_as_it_arrived`;
  - `test_notification_through_remote_has_no_id_and_returns_none`;
  - `test_error_response_reaches_the_caller_with_its_fields`;
  - `test_closed_connection_reaches_the_caller`, for a request and a notification;
  - `test_result_that_does_not_fit_raises_and_the_connection_stays_open`;
  - `test_object_from_remote_is_an_instance_of_the_definition`;
  - `test_remote_gives_one_object_for_each_definition_on_each_peer`;
  - `test_default_implementation_is_sent_and_does_not_run`;
  - `test_remote_refuses_a_class_that_is_not_an_endpoint`;
  - `test_remote_refuses_a_method_with_two_parameters`;
  - `test_remote_refuses_a_plain_method`;
  - `test_remote_of_a_method_with_two_marks_sends_the_nearest`;
  - `test_peer_called_through_a_definition_is_freed`, next to the tests for freeing a peer in `tests/test_peer.py`.

  Verify that they pass. Check each part by taking it out: the conversion of the result, the binding of the arguments, the check of the class, the check of the parameters, the check that the method is async and the object kept on the peer. For the last test, keep the object from `remote` in a list at module level and see the test fail; a list on the peer would only be a cycle, which the garbage collector frees.
- [x] 2.2 Add `JsonRpcEndpoint.remote` (design decision 3). Add to `tests/test_typed_endpoints.py`:
  - `test_attached_endpoint_calls_through_its_remote`;
  - `test_endpoint_without_a_peer_raises`, parametrized over an endpoint that was never attached and one whose `rpc_peer` was set to `None`; it checks that the `RuntimeError` names the class.

  Verify that they pass. Check by removing the test for `None`: the second test gets another error.
- [x] 2.3 Add to `tests/test_typed_endpoints.py`, for several definitions on one peer:
  - `test_two_definitions_with_the_same_python_name_send_their_own_names`;
  - `test_both_directions_on_one_connection`;
  - `test_definition_that_the_peer_also_implements_goes_to_the_other_side`.

  Verify that they pass. Check the first with `functools.cache` keyed on the method name instead of the definition, and the last by letting `remote` return the attached endpoint.
- [x] 2.4 Add `_calls_for_the_type_checker` to `tests/test_typed_endpoints.py`, a function that `mypy` checks and no test runs (design decision 10): `assert_type` for the definition and for the result, an abstract definition without an error, wrong params and an unknown method with `# type: ignore[arg-type]` and `# type: ignore[attr-defined]`, and a plain method as an override of a definition with `# type: ignore[override]`. Verify with `uv run mypy`. Check with `type[E]` instead of `Callable[..., E]`: `mypy` reports `type-abstract`.
- [x] 2.5 Document endpoints in `packages/jsonrpcpeer/README.md`: a definition, implementing it, calling it with `remote`, several endpoints on one peer, and what happens when a method is missing. The section replaces "Class-based Registration". The section "Handler Signatures" says that a handler can be a plain function, and that it runs on the event loop. Rewrite `packages/jsonrpcpeer/examples/class_based_server.py` and `class_based_client.py` on a shared definition in a new file `class_based_api.py` (design decision 9). Add `test_class_based_example_answers_its_definition` to `tests/test_typed_endpoints.py`, which loads the example modules from their directory and calls the server's endpoint over a connection. Verify that it passes, that the code in the README runs as written, and that both example scripts print the expected sums when run by hand. Check by leaving out a method in the example's server class and seeing the test fail.

## 3. The Robot protocol

- [x] 3.1 Add `ServerEndpoint` and `ClientEndpoint` to `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py`, with no method for `robot/trace` (design decision 8). Add `jsonrpcpeer` to the dependencies in `packages/protocol/pyproject.toml`, with `[tool.uv.sources]`, and update `uv.lock` with `uv lock`. Add to `tests/test_protocol.py`:
  - `test_requests_of_the_server_definition`, parametrized over the five requests: the other side gets the name on the wire, and the call returns the result type;
  - `test_notifications_of_the_server_definition`, parametrized over the three notifications;
  - `test_log_of_the_client_definition`;
  - `test_server_definition_names_a_missing_method`, with `run_keyword`.

  Verify that they pass, and that `test_a_package_declares_every_distribution_it_imports` in `tests/test_packaging.py` passes for the scenario on installing the package. Check by changing the name of a message in a definition, and by removing the dependency, which that packaging test must catch.
- [x] 3.2 Let `RobotServerEndpoint` in `packages/server/src/robot_jsonrpcremote_server/_endpoint.py` derive from `ServerEndpoint`, remove its marks and keep `_counted`; `log()` keeps its check and sends through `self.rpc_peer.remote(ClientEndpoint)` (design decision 9). Add `test_server_endpoint_implements_the_definition` to `tests/test_endpoint.py`, and verify that `tests/test_endpoint.py`, `tests/test_server_end_to_end.py` and `tests/test_server_stdio.py` pass. Check by deriving from `JsonRpcEndpoint` again, which fails the new test. No Robot test: see the top of this file.
- [x] 3.3 Let `SimpleRobotServerEndpoint` in `examples/simple-robot-jsonrpcserver/src/simple_robot_jsonrpcserver/__main__.py` derive from `ServerEndpoint` in the same way, with a `log()` that sends through `self.remote(ClientEndpoint)`. Add `test_the_example_server_implements_the_definition` to `tests/test_example_server.py`; `test_the_example_server_handles_a_whole_session` covers the session on the wire. Verify that the file passes. Check by removing `set_log_level` from the example, which fails with a `TypeError` that names it.
- [x] 3.4 Let `_ClientEndpoint` in `src/JsonRpcRemote/__init__.py` derive from `ClientEndpoint`, rename `_log_notification` to `log`, and remove the wrappers; `report_log_level` and `graceful_shutdown` stay and call through a property `server` for `self.remote(ServerEndpoint)`. `_Session` calls through `self.client_endpoint.server` and fills in the values for `robot/initialize` (design decision 9). Update `tests/test_client_logging.py`, and add `test_client_endpoint_implements_the_definition` to `tests/test_client_session.py`. Verify that all tests of the client pass. Check by giving `log` another name: the new test fails on the missing method. No Robot test: see the top of this file.
- [x] 3.5 Update the documentation: `docs/src/content/docs/reference/protocol.mdx` (the package defines both sides as well as the messages, and the example server implements `ServerEndpoint`), the protocol bullet and a group for `jsonrpcpeer` in `docs/src/content/docs/roadmap.mdx`, a sentence on `jsonrpcpeer` in `docs/src/content/docs/index.mdx` and the root `README.md`, `packages/protocol/README.md` (the definitions, and the dependency on `jsonrpcpeer`), `examples/simple-robot-jsonrpcserver/README.md`, and in `CONTRIBUTING.md` the line on `packages/protocol` and a note that the Mypy extension of VS Code brings an older `mypy`. Verify with `npm run build` in `docs/` and `uv run --all-packages bash docs/examples/own-server/run.sh`, and read the implementation against these pages.

## 4. Integration checks

- [x] 4.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [x] 4.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"` for pytest and Robot; verify all pass, as a regression check of the session flow.
- [x] 4.3 Run the unit tests on Python 3.13, 3.14 and 3.15 in scratch environments, with `UV_PROJECT_ENVIRONMENT=<scratch>/venv-<version> UV_PYTHON=<version> uv run --all-packages --dev pytest -q`, and restore the environment afterwards with `uv sync --all-extras --all-packages --dev`; verify all pass.
- [x] 4.4 Run `pyright` once on a scratch file that holds the calls of `_calls_for_the_type_checker` without the `type: ignore` comments (design decision 10); verify that it reports the wrong params, the unknown method and the plain override, and nothing on the abstract definition and on `assert_type`. Run the same file through the `mypy` of the Mypy extension of VS Code, with the same result for the calls of `remote` (design decision 2).
- [x] 4.5 On the Windows test VM, run `uv run --all-packages pytest` and `uv run --all-packages robotcode run` in a copy of the working tree without `__pycache__`, set up with `uv sync --all-extras --all-packages --dev --python 3.12`; verify all pass.
- [x] 4.6 Build the wheels with `uv build --all-packages` and install the three of `jsonrpcpeer`, the protocol and the server into an empty scratch environment; verify that `robot-jsonrpcremote-server --help` runs there and that `from robot_jsonrpcremote_protocol import ServerEndpoint` works.
- [x] 4.7 Build the site with `npm ci` and `npm run build` in `docs/`, and run `uv run --all-packages bash docs/examples/getting-started/run.sh`, `uv run --all-packages bash docs/examples/own-server/run.sh` and `uv run --all-packages bash docs/examples/failures/run.sh`; verify all pass.
- [x] 4.8 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`), once Daniel has given the go:
  - **Subject:** `feat(peer): add typed endpoints, and use them for the Robot protocol`.
  - **Body:** explains that a call named the method, the params and the result type by hand and nothing tied them together, that an abstract definition now states them once for both sides, that `remote` calls a definition and type checkers see it, that `attach_endpoint` finds the marks through the class hierarchy, that the protocol package defines `ServerEndpoint` and `ClientEndpoint` and therefore depends on `jsonrpcpeer`, that the client, the server and the example server use them, that a plain function as a handler no longer runs and then fails, that a notification on a closed connection now fails like a request, and that nothing else changes on the wire. It names the removal of the old `JsonRpcEndpoint` and of `JsonRpcEndpointProtocol`.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`, sync its delta specs into `openspec/specs/jsonrpc-peer` and the new `openspec/specs/protocol`, and commit the archive as its own signed commit, once Daniel has given the go: `docs(openspec): archive add-typed-endpoints`.
- In `playground/anforderungen-und-ideen.md`, set PEER-13 to done.
- Next is `fix-server-library-import` (`playground/umsetzungsplan-review.md`, section 12).
