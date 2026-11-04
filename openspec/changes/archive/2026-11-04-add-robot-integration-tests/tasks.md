# Tasks

Apart from group 1, this change adds tests for behavior that exists, so there is no part of a change to take out. Instead, each new test runs against a copy of the package with the code it covers broken, as the tasks name it, and must fail there. A copy on `PYTHONPATH` wins over the editable install, also for the servers and the nested runs that the suites start.

The suites use the shared server of `atests/__init__.robot`, unless a task says otherwise. Only group 1 changes behavior and documentation. The other groups change nothing on the pages of the site, because these already describe what the tests pin.

A test that reveals a bug is skipped with a message that names the bug, and the bug goes into the backlog for a change of its own. The probes for this plan on 2026-11-03 found none, apart from what `fix-server-argument-resolution` has fixed and the missing line that group 1 adds.

## 1. The line of a keyword, and Libdoc

- [x] 1.1 In `src/JsonRpcRemote/__init__.py`, let `get_keyword_source` return `path:lineno` if the server reports a source and a line, and otherwise the source. In `tests/test_client_session.py`, add `test_keyword_source_comes_with_its_line`, parametrized over a source and a line, a Windows path and a line, a source only, a line only (the source stays `None`), and neither, with a definition scripted on the fake server. Verify that it fails in a copy that returns only the source, and for the line only in a copy that returns `f"{source or ''}:{lineno}"`.
- [x] 1.2 Add `atests/LibdocLib.py`, with documented and tagged keywords, type hints, every kind of argument and a keyword with embedded arguments, and serve it from the shared server. It has no return annotations and no types of its own, because a remote library reports neither to Libdoc. Add `atests/LibdocSpecs.py`, which runs `python -m robot.libdoc` in a process of its own and reads the spec file. Add `atests/libdoc.robot`, with the tests:
  - `Libdoc Describes Remote Keywords Like Local Ones`: for each keyword of the JSON spec, all fields are the same for the file and for `JsonRpcRemote::<uri>::LibdocLib`, and the local spec has a line for each;
  - `The JSON Spec File Holds The Source And The Line Of A Remote Keyword`;
  - `The XML Spec File Holds The Source And The Line Of A Remote Keyword`.

  Verify that the first fails in copies of the client without the line, with `get_keyword_documentation`, `get_keyword_types` and `get_keyword_tags` returning `None`, and without the marker `/` in `get_keyword_arguments`, and that the other two fail in the copy without the line.
- [x] 1.3 In `docs/src/content/docs/roadmap.mdx`, say that the client offers the sources of the keywords with their lines. In `docs/src/content/docs/reference/protocol.mdx`, add to `lineno` of `KeywordDefinition` that it is the line where the keyword is defined, which the client passes to Robot Framework with `source`. These pages show no new example, so no runnable example changes. Verify with `npm run build` in `docs/` and by reading both pages against 1.1.

## 2. Sessions

- [x] 2.1 Add `atests/_nested/scopes/` with the suites `first.robot` and `second.robot`, which import `SessionValueLib` with `rpc_scope=${SCOPE}`. The first remembers a value, and the second compares what it recalls with `${EXPECTED}`. Add to `atests/rpc_scope.robot`, with `Run Nested Suite`:
  - `A GLOBAL Session Keeps Its State Across Suites`: `SCOPE:GLOBAL` and the remembered value;
  - `A SUITE Session Ends With Its Suite`: `SCOPE:SUITE` and `None`.

  No unit test: the state of a session across suites shows only in a Robot run. Verify that the first fails in a copy of the client whose `_end_suite` also ends a `GLOBAL` session, and that the second fails in one whose `_end_suite` ends no session.

## 3. The libraries of a server

- [x] 3.1 Add `atests/default_library.robot`, which imports `JsonRpcRemote` without a library name, with the test `A Client That Names No Library Gets The First Library Of The Server`: `Echo` answers. Verify that it fails in a copy of the server with `self.libraries[1]`.
- [x] 3.2 Add `atests/no_allowlist.robot`, with a server of its own on port 8284 without libraries, through `IsolatedServerControl`, and the tests:
  - `A Server Without Libraries Imports The Library A Client Names`;
  - `A Server Without Libraries Refuses An Import Without A Name`, with the exact message.

  Verify that the first fails in a copy of the server with `if lib_name not in self.libraries`, and that the second fails in one without the check for an empty name. The unit tests for these messages exist; the Robot tests show them through the client.

## 4. Call forms

- [x] 4.1 Add to `atests/ArgumentValuesLib.py` the keywords `positional_only(first, second=2, /)`, `named_only(first, *, key, other="o")` and `all_kinds(first, /, second=2, *rest, key="k", **others)`, each returning the `repr` of what it got. Add to `atests/argument_values.robot`, with the template, tests for: `Var Args` without values, with values of several types and from a list variable; `Var Kwargs` from named arguments and from a dict variable; `Positional Only` with one and two values, and with `first=a`, which stays text, all three without the template, because Robot would take its empty dict variable as a value; `Named Only` with its required and its optional argument; and `All Kinds` with every kind at once. Add without the template `A Missing Named-Only Argument Fails As For A Local Keyword`, with the exact message. Verify that they fail in copies of the client without the marker `/`, without the marker `*`, and without the prefixes `*` and `**` in `get_keyword_arguments`, in one that drops the named arguments and one that sends only the first positional value in `run_keyword`, and in a copy of the server that reports no defaults.

## 5. Python objects

- [x] 5.1 Add to `atests/ArgumentValuesLib.py` the keywords `same_value(value)` and `type_name_of(value)`, a small class `Thing`, `make_thing(value)` and `value_of_thing(thing)`. Add `atests/pickled_values.robot`, which imports the library locally and remotely, with a template that sends a value, checks its type on the server and compares what comes back, and with tests for: `datetime`, `Decimal`, `set`, `bytes` and `tuple`. Add `An Instance Of A Custom Class Reaches The Server` and `An Instance Of A Custom Class Comes Back From The Server`. Verify that they fail in a copy of the client that sends `str(arg)` instead of `value_to_jsonable(arg)`, and in a copy of the server that returns `str(r)` instead of `value_to_jsonable(r)`.

## 6. Unicode and large values

- [x] 6.1 Add `atests/unicode_and_size.robot`, with `ServerProbeLib` and `LogCapture`, and the tests `Unicode In An Argument And A Return Value`, `Unicode In A Log Message`, `A String Of 5 MB Goes Both Ways`, `A List Of 200000 Items Goes Both Ways` and `A Log Message Of 1 MB Arrives`. Verify that the first two fail in a copy of `jsonrpcpeer` whose encoding is not UTF-8, and that the last three fail in a copy that reads a message with `self.reader.read(content_length)` instead of `readexactly`. Check that the suite takes less than a few seconds; if not, make the values smaller.

## 7. HTML messages

- [x] 7.1 Add to `atests/ServerProbeLib.py` the keywords `emit_html_log(message)`, with `logger.info(message, html=True)`, and `print_html(message)`, with `print("*HTML*" + message)`. Let `atests/LogCapture.py` also record which messages are HTML. Add to `atests/log_forwarding.robot` the tests `A Log Message With HTML Stays HTML`, `A Printed Message With The Marker HTML Is HTML` and `A Plain Log Message Is Not HTML`. Verify that the first two fail in a copy of the client with `False` instead of `params.html or False`, and that the third fails in one with `True`.

## 8. Two library instances

- [x] 8.1 Add `atests/_nested/two_instances.robot`, which imports `ServerProbeLib` twice with different arguments, as `First` and `Second`. Add a keyword to `atests/NestedRobot.py` that returns the messages of a test with the names of their keywords. Add `atests/two_instances.robot` with the tests:
  - `Each Instance Has Its Own Arguments`;
  - `The Log Messages Of Each Instance Stay Under Its Keywords`, in a nested run that calls `First` and `Second` in turn.

  Verify that the first fails in a copy of the server with a token that does not change, and that the second fails in one that sends each message to the subscriber that came first.

## 9. Variable files

- [x] 9.1 Add the option `variablefile` to `atests/ServerControl.py`, add `atests/server_vars.py`, and start the shared server with it in `atests/__init__.robot`. Add to `atests/variables.robot` the test `A Server Variable File Is Available During Keyword Execution`. The unit tests do not reach this option, because it only shows in the variables of a running keyword. Verify that it fails in a copy of the server without `variablefiles=args.variablefile or ()`.

## 10. Integration checks

- [x] 10.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [x] 10.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"` for pytest and Robot; verify all pass.
- [x] 10.3 Run the unit tests on Python 3.13, 3.14 and 3.15 in scratch environments, with `UV_PROJECT_ENVIRONMENT=<scratch>/venv-<version> UV_PYTHON=<version> uv run --all-packages --dev pytest -q`, and restore the environment afterwards with `uv sync --all-extras --all-packages --dev`; verify all pass.
- [x] 10.4 On the Windows test VM, run `uv run --all-packages pytest` and `uv run --all-packages robotcode run` in a copy of the working tree without `__pycache__`, set up with `uv sync --all-extras --all-packages --dev --python 3.12`; verify all pass, also the comparison of the sources in `atests/libdoc.robot`.
- [x] 10.5 Build the site with `npm ci` and `npm run build` in `docs/`, and run `uv run --all-packages bash docs/examples/getting-started/run.sh`; verify all pass.
- [x] 10.6 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`), once Daniel has given the go:
  - **Subject:** `feat(client): report the line of a remote keyword, and cover everyday uses in Robot`. The line is visible to users, so the commit belongs in the changelog.
  - **Body:** names what the new suites cover, says that the probes found everything working apart from the line, and explains that `get_keyword_source` now returns `path:lineno`, so that the spec files of Libdoc and listeners get the line.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`, sync its delta spec into `openspec/specs/client`, and commit the archive as its own signed commit, once Daniel has given the go: `docs(openspec): archive add-robot-integration-tests`.
- In `playground/anforderungen-und-ideen.md`, set TEST-6 and CLIENT-16 to done.
