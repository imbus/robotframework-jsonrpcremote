# Tasks

Every new test that covers a fix is run against a copy of the server without that fix, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the servers that the tests start. Tests that pin what stays pass before and after, and the tasks name them.

The Robot suites `atests/argument_values.robot` and `atests/embedded_arguments.robot` compare each case with a local library (design decision 7), and each group adds what its own work changes. They need no new port, because the shared server serves their library.

## 1. Values of keyword calls

- [x] 1.1 In `_runner.py`, add a helper that returns a value as Robot's data, with `robot.utils.escape` (design decision 1), and use it in `_robot_run_keyword` for the positional values, the named values and the names of named arguments. In `tests/test_server_end_to_end.py`, let `_Session.run_keyword` take named arguments, add a keyword `repr_of_named(self, **values)` to `LIBRARY`, and add tests:
  - `test_keyword_gets_a_string_unchanged`, parametrized over `C:\temp\new`, `\d+`, `end\`, `\`, `a\nb` with a real backslash, `${amount}`, `@{items}`, `&{map}`, `%{PATH}` and `${{1+1}}`;
  - `test_keyword_gets_an_equals_sign_in_a_positional_value`: `value=1` for the argument `value` of `Repr Of`. It pins what stays;
  - `test_keyword_gets_strings_in_a_list_or_a_dict_unchanged`: it pins what stays;
  - `test_keyword_gets_a_named_string_unchanged`, over `C:\temp\new` and `${amount}`;
  - `test_keyword_gets_the_name_of_a_named_argument_unchanged`, over `a\b`, `${key}` and `a=b`.

  Verify that they fail in a copy without the helper for positional values (first test), for named values (fourth) and for names (fifth, except `a=b`, which pins what stays).
- [x] 1.2 Add `atests/ArgumentValuesLib.py` with the keywords `echo`, `var_args` and `var_kwargs`, each returning the `repr` of what it got, and add the library to the shared server in `atests/__init__.robot`. Add `atests/argument_values.robot`, which imports the library locally and remotely, with the template keyword `Remote Gives The Same As Local`, and with tests for: a Windows path, a regular expression, a trailing backslash, a lone backslash, an escaped `${amount}`, `@{items}`, `&{map}`, `%{PATH}` and `${{1+1}}`, an escaped equals sign, several values in `Var Args`, a list and a dict that hold such strings, a named value with a path and with `${x}`, and a named argument called `a\b`, `${key}` and `a=b`, also from a variable. Verify that they fail in the copies of 1.1, except those that the task there names as pinning what stays.
- [x] 1.3 In `docs/src/content/docs/reference/protocol.mdx`, add to the section Values that values are final: a client sends them as they are meant to arrive, and the reference server resolves no variables or escapes in them. In `docs/src/content/docs/reference/server.mdx`, add the same to the section Robot Framework on the server, in one sentence after the one about the variables of a remote keyword. These pages show no new example, so no runnable example changes. Verify with `npm run build` in `docs/` and by reading both pages against 1.1.

## 2. Control words

- [x] 2.1 Let the helper leave `AND`, `ELSE`, `ELSE IF`, `AS` and `WITH NAME` as they are (design decision 2). In `tests/test_server_end_to_end.py`, add tests, with `server_without_libraries` and the library `BuiltIn` where they name it:
  - `test_run_keywords_finds_and`: `Run Keywords` with `Log`, `a`, `AND`, `Log` and `b` logs both messages;
  - `test_run_keyword_if_finds_else`: `Run Keyword If` with a false condition, `Fail`, `no`, `ELSE`, `Set Variable` and `fine` returns `fine`;
  - `test_run_keyword_gets_a_string_unchanged`: `Run Keyword` with `Set Variable` and `C:\temp\new` returns that string;
  - `test_keyword_gets_a_control_word_unchanged`, parametrized over the five words, with `Repr Of`.

  Verify that the first two fail in a copy without the exception for control words, and that the third fails in a copy without the helper. The fourth pins what stays.
- [x] 2.2 Add to `atests/ArgumentValuesLib.py` a keyword `words_of_a_variant(self, *words)`, registered with `register_run_keyword` and no arguments to resolve (`run_keyword_variant` only registers for `BuiltIn`), which returns the `repr` of its arguments, and add to `atests/argument_values.robot` the tests `A Run Keyword Variant Finds Control Words`, and one per word with `Echo`. A keyword of its own serves here, because `BuiltIn` as a remote library would take over the `Run Keyword` and `Log` of the suite, with a warning at every call; the unit tests of 2.1 cover `BuiltIn`. Verify that the first fails in the copy of 2.1.

## 3. Library import

- [x] 3.1 Move the building of Robot's data from `_endpoint.py` to `_robot_import_library` (design decision 3): `RobotRemoteContext.import_library` and `_robot_import_library` take `args` and `kw_args`, and the helper of group 1 is used for the positional values, the named values and the names of named arguments, with `str(value)` for named values as today. Adapt the stub in `tests/test_endpoint.py` and the calls in `tests/test_runner.py`. In `tests/test_server_end_to_end.py`, let `_Session.import_library` take `args` and `kw_args`, add a library `InitValuesLib` whose `__init__` takes `*args`, `items: list = None` and `**kwargs` and whose keyword returns their `repr`, and add tests:
  - `test_library_gets_a_string_unchanged`, over `C:\temp\new` and `${amount}`;
  - `test_library_gets_an_equals_sign_in_a_positional_value`: `key=value` arrives as a positional value;
  - `test_library_gets_a_named_string_unchanged`, over `C:\temp\new` and `${amount}`;
  - `test_library_gets_the_name_of_a_named_argument_unchanged`, over `a\b`, `${key}` and `a=b`;
  - `test_library_converts_a_named_list_with_a_backslash`: `items` with `["C:\\temp"]` arrives as that list through its type hint.

  Verify that they fail in a copy without the helper for positional values (first two tests), for named values (third and fifth) and for names (fourth), and that `atests/typed_init.robot`, `atests/init_args.robot` and `atests/init_kwargs.robot` pass unchanged.
- [x] 3.2 Add to `atests/argument_values.robot` two pairs of library imports, local and remote, one with positional values and one with named values and names as in 3.1, and tests that compare what each pair got. Verify that they fail in the copies of 3.1. In `docs/src/content/docs/reference/library.mdx`, add to the section Arguments of the remote library that strings arrive as the suite resolved them, so that a Windows path or a regular expression stays as it is. Verify with `npm run build` in `docs/` and by reading the section against the tests.
- [x] 3.3 Escape the library name and the token in `_robot_import_library` (design decision 4). In `tests/test_server_end_to_end.py`, add `test_library_from_a_path_is_imported`, with `server_without_libraries`, parametrized over a directory named `${folder}` and one named `back\new`; the second is skipped on Windows, where a name cannot hold a backslash and every path holds one. It imports `SECOND_LIBRARY` from there and calls its keyword. Add `atests/library_path.robot` with a server of its own on port 8283 without an allowlist, through `IsolatedServerControl`, and the test `A Library From A Path With The Syntax Of A Variable Is Imported`, which copies `atests/ArgumentValuesLib.py` into a directory under `${TEMPDIR}` named `with${folder}`, imports it with `Import Library`, calls `Echo`, and removes the directory in its teardown. Verify that they fail in a copy without escaping the name, and in one without escaping the token.

## 4. Embedded arguments

- [x] 4.1 In `_robot_run_keyword`, keep from what `find_keywords` returns the normal keyword or the embedded keyword with exactly that name, run an embedded keyword with `LibraryKeywordRunner(kw)`, and remove the branch `Multiple keywords named ...` (design decision 5). In `tests/test_server_end_to_end.py`, add to `LIBRARY` the keywords `Add ${count} Items`, `Copy ${name} To` with the further argument `target`, `Wait ${seconds:\d+} Seconds` with the type `int`, and `Do ${what} Now`, each returning the `repr` of what it got. Add tests:
  - `test_keyword_with_embedded_arguments_gets_the_value`, parametrized over `3`, `[1, 2]`, `C:\temp` and `${amount}`;
  - `test_keyword_with_embedded_arguments_gets_further_arguments`, positional and named;
  - `test_embedded_argument_with_a_type_and_its_own_pattern`: the integer `5`, with its type;
  - `test_keyword_whose_name_fits_other_keywords_is_found`: `Do ${what} Now`, next to `Do ${something}` and `${someone} Now`;
  - `test_name_with_embedded_values_is_answered_with_keyword_not_found`: `Do It Now` is answered with `-32001` and `Keyword 'Do It Now' not found in library 'EndToEndLib'.` It replaces `test_keyword_name_with_several_matches_names_the_library`.

  Verify that the first three fail in a copy with `kw.create_runner(name)`, and that the last two fail in a copy without the filter, on Robot Framework 7.5 and with `--with "robotframework==7.2"`.
- [x] 4.2 Add to `atests/ArgumentValuesLib.py` keywords with embedded arguments, among them two whose patterns overlap and a normal keyword whose name also fits a pattern. Add `atests/embedded_arguments.robot`, which compares local and remote calls without a template, because a template would resolve the names a second time, with tests for: a plain value, a list from a variable, a backslash, `\${amount}`, a type with its own pattern, a further positional and a further named argument, the keyword that fits best among overlapping patterns and the other one, and the normal keyword and the embedded keyword next to it. Verify that they fail in the copy of 4.1 with `kw.create_runner(name)`, except the normal keyword, which pins what stays, and that the keyword that fits best fails in the copy without the filter.
- [x] 4.3 In `docs/src/content/docs/reference/protocol.mdx`, add to `name` in `RunKeywordParams` that a keyword with embedded arguments is called by the name from its definition, such as `Add ${count} Items`, and that `args` starts with their values. In `docs/src/content/docs/roadmap.mdx`, add keywords with embedded arguments to what the client offers. These pages show no new example, so no runnable example changes. Verify with `npm run build` in `docs/` and by reading both pages against 4.1.

## 5. Integration checks

- [x] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [x] 5.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"` for pytest and Robot; verify all pass.
- [x] 5.3 Run the unit tests on Python 3.13, 3.14 and 3.15 in scratch environments, with `UV_PROJECT_ENVIRONMENT=<scratch>/venv-<version> UV_PYTHON=<version> uv run --all-packages --dev pytest -q`, and restore the environment afterwards with `uv sync --all-extras --all-packages --dev`; verify all pass.
- [x] 5.4 On the Windows test VM, run `uv run --all-packages pytest` and `uv run --all-packages robotcode run` in a copy of the working tree without `__pycache__`, set up with `uv sync --all-extras --all-packages --dev --python 3.12`; verify all pass, and that `test_library_from_a_path_is_imported` and `atests/library_path.robot` import from a path with real backslashes.
- [x] 5.5 Build the site with `npm ci` and `npm run build` in `docs/`, and run `uv run --all-packages bash docs/examples/getting-started/run.sh` and `uv run --all-packages bash docs/examples/several-libraries/run.sh`; verify all pass.
- [x] 5.6 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`), once Daniel has given the go:
  - **Subject:** `fix(server): keep values from a client unchanged, and run keywords with embedded arguments`.
  - **Body:** explains that the server resolved finished values a second time, so that paths and regular expressions changed silently, text with `${...}` failed or was replaced on the server, and library paths could not be imported; that keywords with embedded arguments never worked; how the fix keeps control words working; and that a name with values filled in is now answered with `KEYWORD_NOT_FOUND`.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. The Windows jobs confirm on a released Windows what 5.4 showed on the VM, which runs a preview build. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`, sync its delta spec into `openspec/specs/server`, and commit the archive as its own signed commit, once Daniel has given the go: `docs(openspec): archive fix-server-argument-resolution`.
- In `playground/anforderungen-und-ideen.md`, set SERVER-14 and SERVER-22 to done, and add the named values of an import that are not strings as a new item.
- In the proposal of `add-robot-integration-tests`, the next free fixed port is then the one after 8283.
