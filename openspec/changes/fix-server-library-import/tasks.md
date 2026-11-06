# Tasks

Every new test that covers a change is run against a copy of the packages without that part of the change, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the servers that the tests start. Each task names what it takes out for that check. Tests that pin what stays pass before and after, and the tasks name them.

The end-to-end tests go into `tests/test_server_end_to_end.py`. They use the server `server_without_libraries` unless a task names another one, and their libraries are written into `library_directory` like the others. Groups 3 to 5 add no Robot test; each task says why.

## 1. Argument defaults on the server

- [ ] 1.1 In `_runner.py`, build `ArgumentDefinition.default` with a helper (design decision 1). It returns `null`, a string, a boolean, an integer or a finite float of exactly that type as it is, and `arg.default_repr` for every other default. `value_to_jsonable` no longer builds a definition. Add a library `DefaultsLib` with an `Enum` `Button` (`LEFT`, `RIGHT`), an `IntEnum` `Color` (`RED`) and these keywords:
  - `scalars(a=None, b="x", c=True, d=5, e=1.5)`;
  - `containers(a=[1, 2], b={"a": 2})`;
  - `members(a=Button.LEFT, b=Color.RED)`;
  - `floats(a=float("inf"), b=float("nan"))`;
  - `call(f=lambda: 1)`, which returns `f()`.

  Add these tests:
  - `test_defaults_that_are_json_scalars_arrive_as_they_are`: `null`, `"x"`, `true`, `5` and `1.5`;
  - `test_list_and_dict_defaults_arrive_as_their_text`: `"[1, 2]"` and `"{'a': 2}"`;
  - `test_enum_members_as_defaults_arrive_as_their_names`: `"LEFT"` and `"RED"`;
  - `test_library_with_a_default_that_cannot_be_pickled_is_imported`: the default of `f` starts with `<function`;
  - `test_floats_that_json_cannot_carry_arrive_as_their_text`: `"inf"` and `"nan"`;
  - `test_keyword_called_without_the_argument_runs_with_its_real_default`: `Call` returns `1`.

  Change `test_library_definition_describes_the_arguments`: `nested` arrives as `"[1, {'a': 2}]"`, and the test compares `arg.default` without `jsonable_to_value`.

  Verify that the tests fail in these copies:
  - all of them, with `value_to_jsonable(arg.default)`; the new ones fail there because the lambda fails the import;
  - the first, in a copy that sends every default as `default_repr`;
  - the third, in a copy with `isinstance` instead of the exact type, for `RED`;
  - the fifth, in a copy without the check for finite floats.
- [ ] 1.2 Add to `DefaultsLib` the keywords `list_default(value=[1, 2])` and `enum_default(button=Button.LEFT)`, without type hints. Each returns the type and the value it got, such as `list [3, 4]` and `Button RIGHT`. Add `test_string_for_an_argument_with_a_list_default_becomes_a_list` with `[3, 4]` and `test_string_for_an_argument_with_an_enum_default_becomes_the_member` with `RIGHT`. They pin what stays: Robot on the server already converts by the real signature today. Verify that they fail in a copy of the library that gives the argument a string as its default (design decision 6).
- [ ] 1.3 Add `atests/_server_only/ServerOnlyLib.py`. The Robot run cannot import from that folder. The library has an `Enum` `Button`, the keyword `click(button: Button = Button.LEFT)`, which returns `button.name`, and `call(f=lambda: 1)`, which returns `f()`. Add `atests/server_only_library.robot`. It starts a server of its own on port 8286 through `IsolatedServerControl`, with `pythonpath=${CURDIR}${/}_server_only`, and has these tests:
  - `A Keyword With An Enum Default Runs Without The Argument`: `Click` returns `LEFT`;
  - `The Server Converts A String For An Enum Argument`: `Click    RIGHT` returns `RIGHT`;
  - `A Keyword With A Default That Cannot Be Pickled Runs Without The Argument`: `Call` returns `1`;
  - `Libdoc Shows The Default Of A Type That Only The Server Has`: with `Keywords In Json Spec` of `atests/LibdocSpecs.py`, the argument of `Click` reads `button: Button = LEFT`.

  Verify that the suite fails in a copy of the server with `value_to_jsonable(arg.default)`, where the lambda fails the import. With a copy of the library without `call`, `Click` must then be missing on the client.
- [ ] 1.4 Update the docs:
  - `docs/src/content/docs/reference/protocol.mdx`, section Values:
    - the argument defaults leave the list of nested JSON values and the list of values that travel as pickles;
    - the bullet on final values says that Robot Framework on the server still converts them by the signature of the keyword, as for a local library.
  - The same page, `default` in `ArgumentDefinition`: it is any value. The reference server sends `null`, a string, a number or a boolean as it is, and every other default as the text that Libdoc shows for it, such as `LEFT` for a member of an `Enum`.
  - `docs/src/content/docs/reference/server.mdx`, section Robot Framework on the server: Robot Framework converts the arguments by the signature of the keyword, also by the type of a default. For example, the string `[3, 4]` becomes a list for an argument whose default is a list.
  - `docs/src/content/docs/roadmap.mdx`: argument defaults are JSON scalars or the text that Libdoc shows for them.

  No runnable example shows a default, so none changes. Verify with `npm run build` in `docs/` and by reading the pages against 1.1 to 1.3.

## 2. Argument defaults on the client

- [ ] 2.1 In `src/JsonRpcRemote/__init__.py`, let `get_keyword_arguments` hand `arg.default` to Robot unchanged (design decision 2). In `tests/test_client_session.py`, add `test_argument_default_that_holds_a_pickle_arrives_unchanged`. In it, the fake server answers the import with the default `{"__pickled__": "<hex>"}`, whose pickle names a module that does not exist. The keyword is in `get_keyword_names`, and `get_keyword_arguments` returns that dict. `test_argument_default_with_nested_values_arrives_unchanged` pins what stays. Verify that the new test fails in a copy with `jsonable_to_value(arg.default)`.
- [ ] 2.2 Add to `atests/ArgumentValuesLib.py` the keyword `given(f=_NOT_GIVEN, g=_NOT_GIVEN)`. Both defaults are one sentinel object, and the keyword returns the names of the arguments that the call gave. Add to `atests/argument_values.robot` the tests `A Call Without Arguments That Have Defaults Gives None Of Them` and `A Call With Only The Second Of Them Gives Only That One`. With the template `Remote Gives The Same As Local`, they compare `Given` and `Given    g=5` with the local library. A Robot test covers this scenario, because only Robot Framework decides what the client sends (design decision 6). The tests pin what stays. Verify that they fail in a copy of the client whose `run_keyword` takes no named arguments, so that Robot fills in the defaults.
- [ ] 2.3 In `docs/src/content/docs/guides/tcp-and-stdio.mdx`, change the caution: on the client, only return values are read as pickles. The argument defaults go from it, and so does the part about importing `JsonRpcRemote`. Verify with `npm run build` in `docs/` and by reading the caution against 2.1.

## 3. The name of the library

- [ ] 3.1 In `_runner.py`, put `lib.real_name` into `LibraryDefinition.name` (design decision 3). Remove the checks `if lib is None` after `get_library` in `_robot_import_library` and `_robot_run_keyword`. Add these tests:
  - `test_definition_carries_the_name_of_the_library`, with the server `server`: the name is `EndToEndLib`, and the token differs from it;
  - in `test_library_from_a_path_is_imported`: the name is `PathLib`, in both folders;
  - `test_two_imports_of_one_library_carry_the_same_name`, with the server `server`: two connections import `EndToEndLib`, and the names are equal while the tokens differ.

  `test_finalized_library_is_gone` and `test_unknown_library_token_is_answered_with_an_error_that_names_it_and_logged_with_its_traceback` pin what stays: the error for an unknown token comes from Robot Framework. Verify that the new tests fail in a copy with `lib.name`.

  In `docs/src/content/docs/reference/protocol.mdx`, describe `name` in `LibraryDefinition` as the name of the library, as Robot Framework names it without an alias. Verify with `npm run build` in `docs/`.

  There is no Robot test: Robot Framework shows the remote library under the name of `JsonRpcRemote` or its alias, in the log as in Libdoc. The name counts only in the check after a reconnect (3.2).
- [ ] 3.2 In `src/JsonRpcRemote/__init__.py`, let `_definition_changes` compare the name too, and drop the sentence about the name from its docstring. In `tests/fake_server.py`, the default answer to an import names the library as the import asked for it; drop the comment that the real server names it after the token. In `tests/test_client_connect_retry.py`:
  - the case `Lib_2` of `test_definition_changes_name_what_changed` now expects `library attributes changed: name`, and its comment goes;
  - the new test `test_library_of_another_name_after_a_reconnect_fails_the_call` lets the server come back with a definition that differs only in its name. The call fails with the `ConnectionError` stating that the library definition changed.

  Two tests pin what stays: `test_call_after_a_lost_connection_reconnects_and_logs_a_warning`, and `atests/connect_retry.robot`, which reconnects to the same library. Verify that:
  - the two changed tests fail in a copy of the client that leaves the name out of the comparison;
  - `atests/connect_retry.robot` fails with a copy of the server that sends `lib.name` again.

  In `docs/src/content/docs/guides/lost-connections.mdx`, add the name to what the client compares. Verify with `npm run build` in `docs/`.

  There is no new Robot test. Another library behind the same URI also differs in its source or its keywords, which the check notices already. A definition that differs only in its name needs a contrived library, and the unit test covers that case with the fake server.

## 4. The libraries of a client that disconnects

- [ ] 4.1 In `_endpoint.py`, make these changes (design decision 4):
  - `finalize_all` marks the endpoint as disconnected before it copies the tokens;
  - `import_library` finalizes its library at once if the mark is set once the import has completed;
  - both finalize through one helper, which logs a failure at DEBUG.

  In `tests/test_endpoint.py`, add a stub whose `import_library` and `finalize_library` wait for events that the test sets. Add these tests:
  - `test_import_that_completes_after_the_disconnect_finalizes_its_library`;
  - `test_import_that_completes_while_another_library_is_finalized_finalizes_both`;
  - `test_failed_finalization_after_a_late_import_is_logged_at_debug`: the finalization fails with `_shutting_down()`, and the import still returns.

  `test_finalize_all_releases_remaining_tokens` and `test_finalize_all_goes_on_after_a_failure` pin what stays. Verify that:
  - the first two fail in a copy without the finalizing in `import_library`;
  - the second fails in a copy that sets the mark only after the loop;
  - the third fails in a copy whose helper lets the error through.
- [ ] 4.2 Add a library `MarkedLib(marker, delay=0)` (design decision 6). Its `__init__` sleeps `delay` seconds, and its listener writes a line into the file `marker` when the library is closed. Each of these tests waits for the lines with `wait_until` and a time limit of 10 s while the server goes on running, and then counts them:
  - `test_library_of_a_client_that_disconnects_is_finalized_once`: an import, then a disconnect without finalizing gives one line. It pins what stays;
  - `test_library_whose_import_runs_when_the_client_disconnects_is_finalized_once`: an import of 1 s and a disconnect after 0.3 s give one line;
  - `test_both_libraries_are_finalized_when_the_client_disconnects_during_the_second_import`: one library is imported, then a second import of 1 s runs, and the client disconnects after 0.3 s. Each file gets one line.

  Verify that:
  - the last two fail in a copy without the finalizing in `import_library`;
  - the last one also fails in a copy that sets the mark only after the loop;
  - the first fails in a copy without the finalizing in `finalize_all`.

  In `docs/src/content/docs/reference/protocol.mdx`, add to step 5 of the session: the reference server finalizes the libraries of a connection that ends without `robot/finalize_library`, also one whose import was still running. Verify with `npm run build` in `docs/`.

  There is no Robot test: all of this happens after the client is gone, so nothing of it reaches the client's Robot Framework run.

## 5. The messages of library imports

- [ ] 5.1 In `_runner.py`, let `_hook_loop` turn Robot Framework's message cache off as its first step, with `LOGGER.disable_message_cache()` (design decision 5). Add a library `MessageCacheLib` with the keyword `cached_messages_naming(name)`. It counts the messages in `LOGGER._message_cache` whose text holds `name`. It reads the attribute directly, and counts none if the attribute is `None`. Add the test `test_imports_leave_no_messages_in_the_server`: 100 sessions import `EndToEndLib` and finalize it, and then the count for `EndToEndLib` is 0. Verify that it fails in a copy without the call, with a count above 100.

  There is no Robot test: the messages stay in the server process. No page describes the growth, so no page changes.

## 6. Integration checks

- [ ] 6.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [ ] 6.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"` for pytest and Robot. Verify that all pass, `atests/libdoc.robot` included: its remote spec has to stay equal to the local one with the defaults as text.
- [ ] 6.3 Run the unit tests on Python 3.13, 3.14 and 3.15 in scratch environments, with `UV_PROJECT_ENVIRONMENT=<scratch>/venv-<version> UV_PYTHON=<version> uv run --all-packages --dev pytest -q`. Restore the environment afterwards with `uv sync --all-extras --all-packages --dev`. Verify that all pass.
- [ ] 6.4 On the Windows test VM, run `uv run --all-packages pytest` and `uv run --all-packages robotcode run` in a copy of the working tree without `__pycache__`, set up with `uv sync --all-extras --all-packages --dev --python 3.12`. Verify that all pass, the disconnect tests and `atests/server_only_library.robot` included.
- [ ] 6.5 Build the site with `npm ci` and `npm run build` in `docs/`. Run `uv run --all-packages bash docs/examples/<name>/run.sh` for `getting-started`, `own-server`, `connect-retry` and `several-libraries`. Verify that all pass.
- [ ] 6.6 Once Daniel has given the go, commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`):
  - **Subject:** `fix(server): send argument defaults as text, name the library, and finalize late imports`.
  - **Body:** explains, in this order:
    - a default that could not be pickled failed the import, and a default whose class only the server had cost the keyword on the client;
    - defaults are now JSON scalars or the text that Libdoc shows, and the client decodes no pickle in them, so importing a library runs no code from the server on the client;
    - for such defaults, Robot on the server now converts the arguments;
    - the definition named the library after its token; it now names it as Robot Framework does, and the client compares the name after a reconnect;
    - a library whose import completed after its client had disconnected stayed loaded; it is now finalized;
    - Robot's message cache grew with every import; the server now turns it off.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`, and sync its delta specs into `openspec/specs/server` and `openspec/specs/client`. Once Daniel has given the go, commit the archive as its own signed commit: `docs(openspec): archive fix-server-library-import`.
- In `playground/anforderungen-und-ideen.md`, set SERVER-6, SERVER-8, SERVER-10 and SERVER-12 to done. Set CLIENT-12 to partly done: the defaults are done, and the return values remain.
- Next are `add-stdio-streams` and then `add-windows-stdio` (`playground/umsetzungsplan-review.md`, section 13). Two later changes depend on this one, and their `/opsx:update` checks it:
  - the proposal of `encode-json-values-natively` no longer needs to cover defaults;
  - `clarify-global-library-scope` builds on the changed import path.
- The next free fixed port for the Robot suites is then 8287.
