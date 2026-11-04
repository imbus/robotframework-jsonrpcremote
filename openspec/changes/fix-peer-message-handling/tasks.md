# Tasks

Every new test that covers a change is run against a copy of the packages without that part of the change, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the servers that the tests start. Tests that pin what stays pass before and after, and the task says so. Each task names the part to take out.

The unit tests of the peer go into `tests/test_peer.py`. Task 1.1 adds a fixture `raw_peer` there: a peer with a `StreamReader` that the test feeds, a `_FakeWriter`, an `on_problem` that collects the texts, and the handlers `echo` and `changed`. A helper returns the answers from what the writer got.

The peer's behavior can be seen from Robot Framework only through a server that breaks the protocol. Task 4.4 therefore adds a raw server and one Robot suite for what a Robot user sees (design decision 11). Groups 1 to 3 add no Robot test of their own for that reason.

## 1. Reading messages

- [ ] 1.1 Add `_report_problem` and the option `on_problem` to `JsonRpcPeer` (design decision 4). Split the read loop into `_read_message`, `_read_header_part` and `_read_header_line`, and check the length with `[0-9]{1,18}` (design decisions 1 and 3). A header part without a valid length is reported and gets no answer. Add to `tests/test_peer.py`:
  - `test_invalid_length_is_reported_and_not_answered`, parametrized over `abc`, `-5`, `+5`, `1.5`, `1_000`, an empty value and 5000 digits: nothing is written, the problem holds the value, and the next message is handled;
  - `test_missing_length_is_reported_and_not_answered`;
  - `test_empty_line_between_two_messages`;
  - `test_waiting_request_survives_an_invalid_length`;
  - `test_message_after_content_with_a_line_end_is_handled`;
  - `test_message_after_content_without_a_line_end_is_reported`;
  - `test_problem_is_logged_without_a_callback`;
  - `test_problem_goes_to_the_callback_and_the_log`;
  - `test_exception_of_the_callback_is_logged_and_reading_goes_on`.

  Verify that they fail in a copy that closes on a bad length, as the code does today. Take out the regular expression in a copy, and verify that the first test fails for `+5` and `1_000`.
- [ ] 1.2 Match header names as in HTTP (design decision 1): `partition(":")`, `strip()`, `lower()`, and ASCII with `errors="replace"`. Add `test_header_name_is_matched_without_regard_to_case`, over `content-length` and `CONTENT-LENGTH`, `test_space_after_the_colon_is_optional`, `test_whitespace_around_the_value_is_ignored`, `test_charset_with_a_different_spelling`, `test_header_field_that_the_peer_does_not_know_is_ignored`, also without a colon, and `test_byte_outside_ascii_in_an_unknown_header_field`. Verify that they fail in a copy with the exact match of today, and in a copy without `errors="replace"` for the last one.
- [ ] 1.3 Drop a line above the reader's limit (design decision 2). Add `test_long_content_without_a_line_end_keeps_the_connection_open`, which is followed by a line end and a message that is handled, and `test_long_unknown_field_before_and_after_the_length`, whose message is handled. Verify that they fail in a copy without the `except asyncio.LimitOverrunError`, and that the second one fails in a copy that returns `""` for such a line.
- [ ] 1.4 Answer content that cannot be read with `-32700` and `id: null`, from a task (design decisions 6 and 8): `_start_task`, `_answer_problem`, and a `handle_message` that catches `ValueError` and `RecursionError` when it parses. Add `test_charset_that_cannot_be_used_is_answered_with_a_parse_error`, over `nope`, `hex` and a name with a null byte, `test_content_not_valid_in_its_charset_is_answered_with_a_parse_error`, `test_content_that_is_not_json_is_answered_with_a_parse_error`, over `{not json`, deep nesting, a huge integer and empty content, `test_other_text_encoding_is_decoded`, over `latin-1` and `utf8`, and `test_waiting_request_survives_content_that_cannot_be_read`. Change `test_message_that_cannot_be_parsed_has_no_traceback_by_default_and_is_not_logged` to read what is written and to expect a report, renamed to `..._and_is_reported`, and `test_peer_configured_to_send_tracebacks_sends_that_of_a_message_that_cannot_be_parsed` to read what is written. Verify that the new tests fail in a copy that catches only `JSONDecodeError` and has no `except` around the decoding.
- [ ] 1.5 Skip a message above the size limit and answer it with `-32600` and `id: null` (design decision 6). Add `test_message_above_the_limit_is_skipped_and_answered`, `test_content_above_the_limit_in_several_parts_is_skipped`, with more than 64 KiB in parts, and `test_waiting_request_survives_a_message_above_the_limit`, which replaces `test_oversized_incoming_message_fails_the_request_without_a_cause`. Verify that they fail in a copy that closes the connection, as today.
- [ ] 1.6 In `docs/src/content/docs/reference/protocol.mdx`, section Framing, add that header names are matched without regard to case, that the space after the colon is optional, and what happens to a message without a valid length; in section Errors, extend the rows `-32700` and `-32600`. In `packages/jsonrpcpeer/README.md`, section Protocol & Framing, say the same briefly, and describe `on_problem` under Error Handling. Verify in 5.5 that the site builds.

## 2. Telling messages apart

- [ ] 2.1 Rewrite `process_single_message` with the order of design decision 7, and add `_is_usable_id` and `_invalid_message`. Add:
  - `test_message_with_neither_a_method_nor_an_id_is_invalid`, over `{"jsonrpc":"2.0"}` and `{"jsonrpc":"2.0","params":{}}`;
  - `test_method_that_is_no_string_is_invalid`: `[]` with the `id` `1` keeps its `id`, and `1` without an `id` gets `id: null`;
  - `test_params_that_are_neither_an_array_nor_an_object_are_invalid`, over a string, a number and a boolean, with and without an `id`: no handler is called;
  - `test_array_as_params_reaches_the_handler`, which pins what stays;
  - `test_null_params_count_as_missing`, which pins what stays;
  - `test_id_of_another_type_is_invalid`, over an object, `true` and `1.5`: the handler is not called;
  - `test_null_id_with_a_method_is_invalid`: the handler is not called;
  - `test_message_that_is_no_object_is_invalid`;
  - `test_other_version_is_invalid`, with and without an `id`, over a missing `jsonrpc` and `1.0`: no handler is called;
  - `test_request_with_a_string_or_integer_id_keeps_its_id`;
  - `test_notification_calls_its_handler_and_sends_nothing`.

  `test_invalid_jsonrpc_version` and `test_non_dict_payload` pin what stays. Verify that the new tests fail in the unchanged code where they differ from it: the invalid ones except those that are `-32600` today, and that the invalid ones are reported.
- [ ] 2.2 Let `process_notification` return nothing and report failures (spec: A notification is never answered). Add `test_failing_notification_handler_is_reported_and_not_answered`, `test_params_of_a_notification_that_cannot_be_converted_are_reported_and_not_answered`, `test_unknown_notification_is_ignored`, with the entry at DEBUG level and no report, and `test_attached_endpoint_gets_its_notifications`, which pins what stays. Change `test_error_that_a_notification_handler_raises_is_not_logged` to expect a report and no answer, renamed to `test_error_that_a_notification_handler_raises_is_reported_and_not_answered`. Verify that the first three and the renamed test fail in a copy with the responses of today.
- [ ] 2.3 Make `_handle_response` synchronous, without any answer (design decision 7). Add:
  - `test_response_of_another_version_fails_the_waiting_request`, over a missing `jsonrpc` and `1.0`: `-32600`, a message that names the version, nothing written;
  - `test_invalid_response_that_no_request_waits_for_is_reported`, over no `jsonrpc` and neither a result nor an error;
  - `test_response_with_an_id_of_another_type_is_reported_and_not_answered`;
  - `test_null_id_with_neither_a_result_nor_an_error_is_reported`;
  - `test_error_response_without_an_id_is_reported`, with its code and message;
  - `test_valid_response_that_no_request_waits_for_is_ignored`;
  - `test_response_to_a_request_that_was_just_cancelled_is_ignored`;
  - `test_null_error_is_no_error`, with the four scenarios of the spec.

  Verify that they fail in a copy with the `match` statement of today, and `test_response_to_a_request_that_was_just_cancelled_is_ignored` in a copy without the check of `done()`.
- [ ] 2.4 Add tests for the timeout, which needs no new code: `test_request_without_a_response_in_time_fails_with_a_timeout`, where the next request gets its response, and `test_response_after_the_timeout_is_ignored`. They pin what stays, except that the second one fails in a copy with the answer of a response.
- [ ] 2.5 Remove `JsonRpcInvalidRequestError` from `peer.py` and from the exports of `packages/jsonrpcpeer/src/jsonrpcpeer/__init__.py`. Leave `JsonRpcEndpoint` as it is: it belongs to `add-typed-endpoints`. Verify with `grep -rn JsonRpcInvalidRequestError src packages tests docs examples`, which finds nothing, and with `uv run mypy`.
- [ ] 2.6 In `docs/src/content/docs/reference/protocol.mdx`, section Errors, name in the row `-32600` the invalid messages of the spec, and say that a notification and a response are never answered. Verify in 5.5 that the site builds.

## 3. Sending

- [ ] 3.1 Take the default from `JsonRpcResponse.result` (design decision 10). Add `test_handler_without_a_result_answers_with_a_null_result`, with `"result":null` in what is written, and with `None` for the caller in a `peer_pair`. Verify that it fails in a copy with the default.
- [ ] 3.2 Split sending into `_encode_message`, `_write_frame`, `_encode_response` and `_write_answer`, and remove the last `except Exception` of `handle_message` (design decision 8). Add `test_result_that_cannot_be_written_is_answered_and_logged`, `test_response_above_the_size_limit_is_answered_and_logged` and `test_remote_side_going_away_during_a_handler_leaves_nothing_behind`, with a writer whose `drain` raises `ConnectionResetError`: a single write, no error in the log, and no exception that asyncio reports as never retrieved. Change `test_request_with_extra_field_error_code` to read what is written. `test_request_gets_an_answer_when_its_error_response_cannot_be_sent` pins what stays. Verify that the first two fail in a copy without the log, and the third in a copy that sends a second error.
- [ ] 3.3 Answer a batch with `_handle_batch`, with each response encoded on its own (design decision 9). Add `test_batch_with_requests_and_notifications`, `test_batch_of_notifications_sends_nothing`, `test_batch_with_a_failing_notification`, `test_batch_with_an_invalid_element`, `test_batch_of_responses_gives_each_request_its_response` and `test_batch_with_a_result_that_cannot_be_written`. Change `test_empty_batch_returns_error` to read what is written. Verify that the last new test fails in a copy that encodes the array as a whole. The others pin what stays, except for the answer to the failing notification.
- [ ] 3.4 In `tests/test_server_end_to_end.py`, add `test_client_that_goes_away_during_a_keyword_leaves_no_error_in_the_log`: a raw client aborts its connection while a keyword runs, and the stderr of the server has neither `never retrieved` nor `Connection lost` after the keyword has ended. Verify that it fails in a copy that sends a second error. It adds no Robot test, because it shows only in the log of the server.
- [ ] 3.5 In `docs/src/content/docs/reference/protocol.mdx`, say that a batch is an array, as in JSON-RPC 2.0, and that it is answered with one array. In `packages/jsonrpcpeer/README.md`, change the entry on errors that cannot be sent to cover results and batches. Verify in 5.5 that the site builds.
- [ ] 3.6 Let `default_encoding` set only what the peer sends (design decision 12): decide on the `Content-Type` field with `codecs.lookup` when the peer is created, write it in `_write_frame`, and read a message without a charset as UTF-8. Add `test_peer_with_another_encoding_names_its_charset`, `test_peer_with_utf8_sends_no_content_type`, over `utf-8`, `utf8` and `UTF-8`, `test_message_without_a_charset_is_read_as_utf8`, by a peer with `latin-1`, `test_peers_with_different_encodings_understand_each_other` and `test_unknown_default_encoding_fails_when_the_peer_is_created`. Verify that the first and the fourth fail in a copy without the field, and the third and the fourth in a copy that reads with `default_encoding`. In `packages/jsonrpcpeer/README.md`, describe `default_encoding`. It adds no Robot test, because neither the client nor the server offers the option.

## 4. What a Robot user sees

- [ ] 4.1 Pass `console` on (design decision 10): `_write_log` and `_LogSink.submit` take `bool | None`, `_log_notification` passes `params.console`, and `log()` in `_endpoint.py` and in the example server default to `None`. In `tests/test_client_logging.py`, let `_RecordingLogger` and `_Written` take `None`, and add `test_console_value_is_passed_to_write_where_supported`, over `None`, `True` and `False`, and `test_message_without_a_console_value_stays_with_robot_framework_before_7_4`. In `tests/test_server_end_to_end.py`, change `test_forwarded_message_keeps_its_level_and_html_and_is_not_for_the_console` to expect `None`, renamed to `test_forwarded_message_keeps_its_level_and_html_and_leaves_the_console_to_the_client`. Verify that they fail in a copy with `params.console or False`.
- [ ] 4.2 Add `_report_peer_problem`, and pass it in `_start_peer` with `functools.partial` (design decision 4). In `tests/fake_server.py`, add a scripted answer `RawFirst`, which writes bytes to the connection before the answer. In `tests/test_client_logging.py`, add `test_problem_of_the_peer_is_written_as_an_error`, with the URI, the problem, level ERROR and `console` `None`, and `test_keyword_call_waits_on_after_a_problem_of_the_peer`. Verify that they fail in a copy without `on_problem`, and that `test_the_peer_of_an_ended_session_is_freed` in `tests/test_client_session.py` fails in a copy that passes a bound method of the session.
- [ ] 4.3 Add `atests/ConsoleMessagesLib.py`, with keywords that log at INFO, WARN and ERROR, and add it to the shared server in `atests/__init__.robot`. Let `atests/NestedRobot.py` also return the console output of a run. Add `atests/console_messages.robot`, which runs `atests/_nested/console_messages.robot` once with the library imported locally and once through JsonRpcRemote, and compares: `WARN` and `ERROR` are on the console in both runs, and `INFO` in neither. Verify that the test for the remote run fails in a copy with `params.console or False` on Robot Framework 7.5, and that it passes with `--with "robotframework==7.2"`.
- [ ] 4.4 Add `atests/RawServerLib.py`, a raw server on port 8285 with a mistake to choose, and `atests/protocol_mistakes.robot`, which runs `atests/_nested/raw_server.robot` in its own process, so that the errors stay out of the outer run. Add these tests:
  - `Error For A Message Without A Valid Length During A Keyword Call`: the keyword passes after a delay, the error is under the keyword, among the execution errors and on the console, and it names the URI and `abc`;
  - `Error For A Message Without A Valid Length While The Library Is Imported`: the import fails with a timeout, and the execution errors hold `abc`;
  - `Error For A Log Message With Params That Cannot Be Converted`: the execution errors name `robot/log`;
  - `Error For An Error Response Without An Id`: the execution errors hold the code and the message;
  - `Response With A Null Error Counts As Success`;
  - `Header Name In Lower Case Works`;
  - `Response Without Jsonrpc Fails The Import With Its Reason`: at once, with a message that names the version;
  - `Warning That Is Not For The Console`: in the log and not on the console; it is skipped before Robot Framework 7.4.

  Verify that they fail in a copy of the matching part: without `on_problem`, with the `match` statement of today, with the exact header match, and with `params.console or False`.
- [ ] 4.5 In `docs/src/content/docs/reference/protocol.mdx`, section Log messages, say what `console` means with `true`, with `false` and without a value. In `docs/src/content/docs/guides/failures.mdx`, section Errors that are not failures of a keyword, say that a problem with a message from the server appears as an error in the log and on the console. In `docs/src/content/docs/roadmap.mdx`, add to the protocol part that a message that cannot be read does not end the session. Verify in 5.5 that the site builds.

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [ ] 5.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"` for pytest and Robot; verify all pass.
- [ ] 5.3 Run the unit tests on Python 3.13, 3.14 and 3.15 in scratch environments, with `UV_PROJECT_ENVIRONMENT=<scratch>/venv-<version> UV_PYTHON=<version> uv run --all-packages --dev pytest -q`, and restore the environment afterwards with `uv sync --all-extras --all-packages --dev`; verify all pass.
- [ ] 5.4 On the Windows test VM, run `uv run --all-packages pytest` and `uv run --all-packages robotcode run` in a copy of the working tree without `__pycache__`, set up with `uv sync --all-extras --all-packages --dev --python 3.12`; verify all pass, also the raw server on port 8285.
- [ ] 5.5 Build the site with `npm ci` and `npm run build` in `docs/`, and run `uv run --all-packages bash docs/examples/getting-started/run.sh`, `uv run --all-packages bash docs/examples/own-server/run.sh` and `uv run --all-packages bash docs/examples/failures/run.sh`; verify all pass. Compare the implementation with the pages of 1.6, 2.6, 3.5, 3.6 and 4.5.
- [ ] 5.6 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`), once Daniel has given the go:
  - **Subject:** `fix(peer): handle malformed messages as the LSP does, and keep the connection open`.
  - **Body:** explains that notifications were answered, that header names and spacing were matched exactly, that malformed input closed the connection or put the stream out of step without a trace, that problems in the client never reached Robot Framework, that responses with `"error": null` or without `jsonrpc` were misread, that `None` sent no `result`, that invalid messages got a wrong answer or none, also `params` that are neither an array nor an object, that a peer with another `default_encoding` did not name its charset, that a client going away left a traceback in the server's log, and that warnings of remote keywords were missing on the console from Robot Framework 7.4 on. It names the removal of `JsonRpcInvalidRequestError` and the new option `on_problem`.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`, sync its delta specs into `openspec/specs/jsonrpc-peer`, `openspec/specs/client` and `openspec/specs/server`, and commit the archive as its own signed commit, once Daniel has given the go: `docs(openspec): archive fix-peer-message-handling`.
- In `playground/anforderungen-und-ideen.md`, set PEER-2, PEER-3, PEER-8 to PEER-12, PEER-14 to PEER-17, TEST-4 and CLIENT-18 to done.
- Next is `add-typed-endpoints` (`playground/umsetzungsplan-review.md`, section 11b).
- The proposal of `harden-server-network-defaults` still says that a larger message closes the connection; adapt it at its `/opsx:update`.
- The next free fixed port for a Robot suite is then the one after 8285.
