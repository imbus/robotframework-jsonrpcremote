# Tasks

Every new test that covers a fix is run once against the code without that fix, and must fail there. Tests that pin behavior this change leaves alone pass before and after, so there is no part of the change to take out for them. They come first, in group 1, so that the fixes happen under their protection.

## 1. Tests of what stays

No Robot test in this group: the module shows in Robot Framework only through the protocol, which the existing suites already exercise, and group 4 adds what is new there.

- [ ] 1.1 Take over RobotCode's tests from `tests/robotcode/core/test_dataclasses.py` into `tests/test_json_helpers.py`, in sections, with their names and dataclasses (design decision 10). Leave out `test_really_complex_data` and put `test_nested_dataclasses_in_camel_case_round_trip` in its place: a tree of dataclasses with `CamelSnakeMixin`, optional fields, a list of dataclasses, a dict, an enum, a literal and a union, written with `as_json` and read back with `from_json`. Verify that all pass against the unchanged module. They cover these scenarios:
  - Unknown keys of an object count only in strict mode: all;
  - `from_dict` picks the class that fits an object best: all except the text in Several classes fit equally well, which 3.5 adds;
  - `from_dict` fills a class from the keys of an object: Keys in any order, Fields with defaults, `null` for a class;
  - Field names in JSON follow the alias and the case of the class: Alias, for `as_json` and `from_dict`.
- [ ] 1.2 Add tests to `tests/test_json_helpers.py` for the rest of what stays, and verify that all pass against the unchanged module:
  - `from_dict` converts JSON data to the target type: all;
  - `from_dict` fills a class from the keys of an object: Nested classes, Class with annotated fields that is no dataclass, Required field without a key;
  - Errors name the path of the wrong value: all;
  - Field names in JSON follow the alias and the case of the class: Alias for `as_dict`, Camel case, Field names without encoding;
  - `as_json` writes dataclasses, enums, tuples and sets as JSON: Collections without `frozenset`, Enum, Formats;
  - `as_json` leaves out some fields of a dataclass: all;
  - `as_dict` writes a dataclass as a dict of plain values: all;
  - `remove_defaults` leaves out fields that have their default: Value from `default`, Field without a default, Nested dataclass;
  - `validate_types` reports what does not fit: Element of a list, Key and value of a dict, Literal, Boolean for `int`, No type or `Any`;
  - `ValidateMixin` converts and checks the fields of a dataclass: all;
  - The case helpers convert names between snake case and camel case: all;
  - Values other than JSON scalars travel as pickles: all.

## 2. `from_dict`

Tasks 2.3 to 2.6 add no Robot test: the protocol has no target of these kinds, so Robot Framework cannot reach them.

- [ ] 2.1 In the object path of `from_dict`, skip a class without type hints that is no dataclass, and remove the check for `bool` in `_get_signature_cached` (design decision 1). Verify with tests in `tests/test_json_helpers.py` for all scenarios of A JSON object only becomes a class with fields. Without the condition, Object for a number and Object for a collection that is no mapping fail; without its dataclass check, Dataclass without fields fails. It adds no Robot test here: until 4.1, nested values fail the import, and 4.1 adds the Robot tests for them.
- [ ] 2.2 In `__from_dict_handle_basic_types`, look at `bool` first (design decision 2). Verify:
  - tests in `tests/test_json_helpers.py` for all scenarios of A boolean is not a number for `from_dict`;
  - the new test `Boolean Comes Back As A Boolean` in `atests/types.robot`, which checks `${result} is True`, because `Should Be Equal` takes `1.0` and `True` as equal. This covers the client scenario Boolean as a return value together with a test in `tests/test_client_session.py` in 4.1;
  - with only the `int` half of the fix, the new test, the existing test `Boolean Keeps Its Type On The Server` and the scenario Boolean in a union with numbers fail.
- [ ] 2.3 In the handler table and `__from_dict_handle_sequence`, give a list for `Sequence`, `MutableSequence`, `Collection` and `Iterable` (design decision 3). Verify with tests in `tests/test_json_helpers.py` for all scenarios of Abstract collection types give a list; without the fix, Abstract collection type fails.
- [ ] 2.4 Add `__from_dict_handle_tuple` in front of the sequence handler, and remove `Ellipsis` from the handler table (design decision 3). Verify with tests in `tests/test_json_helpers.py` for all scenarios of Tuple types check their length and positions and A named tuple takes a list by position; without the handler, Wrong type at a position, Wrong length, Tuple of any length, Fitting list of a named tuple and Written and read back fail.
- [ ] 2.5 In `__from_dict_handle_mapping`, convert each key to the key type (design decision 5). Verify with tests in `tests/test_json_helpers.py` for all scenarios of Dict keys are checked against the key type; without the fix, Key of the wrong type, Number as a string and Enum as a key fail.
- [ ] 2.6 In the first loop of `from_dict`, keep the first `TypeError` of a handler, go on with the next type, and raise it if nothing fits (design decision 4). Verify with tests in `tests/test_json_helpers.py` for all scenarios of A union tries its other types when an element does not fit; without the fix, Union of list types, Union of tuple types and Union of dict types with classes fail, and without raising the kept error, No type fits fails.
- [ ] 2.7 In `packages/jsonrpcpeer/README.md`, update the list of supported types and the section Type Conversion & Validation: unions, literals, enums, tuples and named tuples, abstract collection types, that a boolean is no number, that an object only becomes a class with fields, and that dict keys are checked. Review the text against the tests of this group.

## 3. `validate_types`, the writers and the cleanup

No Robot test in this group: client and server use neither `validate_types` nor `as_dict`, the server encodes its results before `as_json` sees them, and the corrected texts reach Robot Framework only in a failure that this change does not touch (backlog JSON-5).

- [ ] 3.1 In `validate_types`, use `is_union(origin)` (design decision 6). Verify with tests in `tests/test_json_helpers.py` for all scenarios of `validate_types` treats both spellings of a union alike. First call in a process runs in a subprocess with `sys.executable` (design decision 10). Without the fix, on Python 3.12, First call in a process and Field of a dataclass fail.
- [ ] 3.2 Add the helper for the elements of a sequence, with the length and positions of a tuple, and remove `Ellipsis` as a type from `validate_types` (design decision 6). Verify with tests in `tests/test_json_helpers.py` for the scenarios Positions of a tuple, Length of a tuple and Tuple of any length; without the fix, all three fail.
- [ ] 3.3 In `_default`, check `(set, frozenset)` (design decision 9). Verify with the scenario Collections for `frozenset` in `tests/test_json_helpers.py`; without the fix, it fails.
- [ ] 3.4 Add `_has_default_value` and use it in `_handle_dataclass` (design decision 7). Verify with the scenario Value from `default_factory` in `tests/test_json_helpers.py`; without the fix, it fails.
- [ ] 3.5 Correct the two texts and remove the unreachable code and the helpers nobody calls (design decision 9). Verify:
  - tests in `tests/test_json_helpers.py` for the exact texts in Several classes fit equally well and Value that JSON cannot hold, which fail with the old texts;
  - full branch coverage with `COVERAGE_FILE=<scratch>/.coverage uv run --all-packages --with coverage coverage run --branch --source=jsonrpcpeer.json_helpers -m pytest tests/test_json_helpers.py`, and `coverage report -m --include='*/json_helpers.py'` with the same environment. Add tests for what is still missing. Where a branch turns out to be unreachable, such as the `except ValueError` around the signature if no class reaches it, remove it. Name in the report of this task whatever stays uncovered, with the reason.

## 4. `AnyType` and nested values

- [ ] 4.1 In `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py`, change `AnyType` to `SimpleType | list[Any] | dict[str, Any]` (design decision 8). Verify, and see each new test fail without this change:
  - `tests/test_protocol.py`: `from_dict` keeps `[{"id": 1}]`, `{"a": [1, 2]}`, `[[1, 2]]` and `[{}]` for `AnyType` and for the fields `RunKeywordParams.args`, `RunKeywordParams.kwargs` and `RunKeywordResult.result`, and keeps `True` as `True`;
  - `tests/test_client_session.py`, with `FakeServer.script`: the client scenarios Return value with nested objects, Argument default with nested values and Boolean as a return value. Only a server that is not in Python sends a nested return value or default as plain JSON, because the Python server pickles lists and dicts until `encode-json-values-natively`, so these two have no Robot test;
  - `tests/test_server_end_to_end.py`, with a new keyword of `EndToEndLib` that returns the `repr()` of its argument: the server scenarios Argument of a keyword and Boolean as an argument of a keyword, sent as plain JSON. The client pickles lists and dicts for now, so the first has no Robot test, and the second is `Boolean Keeps Its Type On The Server` in `atests/types.robot`;
  - `atests/init_args.robot`: a third positional argument `${{[{"id": 1}]}}` for `ServerProbeLib` and the new test `Init Arguments Keep Their Nesting`. This covers the server scenario Argument of a library import;
  - `atests/typed_init.robot` and `atests/TypedInitLib.py`: a new optional argument `nested: dict | None = None`, set to `${{ {"a": [1, 2]} }}` in the suite, and the new test `Nested Named Init Argument Arrives As A Dict`. This covers the server scenario Named argument of a library import.
- [ ] 4.2 Update the documentation site. On `docs/src/content/docs/reference/protocol.mdx`, say that JSON values may be nested to any depth. On `docs/src/content/docs/reference/library.mdx`, say that positional values keep their nesting. In the section Protocol of `docs/src/content/docs/roadmap.mdx`, add it as available. Review the pages against the tests of 4.1; no example in `docs/examples/` shows this, and `docs/examples/own-server` still passes in 5.4.

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass.
- [ ] 5.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"` for pytest and Robot; verify all pass.
- [ ] 5.3 Run the unit tests on Python 3.13, 3.14 and 3.15 in scratch environments, with `UV_PROJECT_ENVIRONMENT=<scratch>/venv-<version> UV_PYTHON=<version> uv run --all-packages --dev pytest -q`, and restore the environment afterwards with `uv sync --all-extras --all-packages --dev`; verify all pass.
- [ ] 5.4 Build the site with `npm ci` and `npm run build` in `docs/`, and run `uv run --all-packages bash docs/examples/own-server/run.sh` and `uv run --all-packages bash docs/examples/getting-started/run.sh`; verify all pass.
- [ ] 5.5 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`):
  - **Subject:** `fix: reject JSON that does not fit its type, and keep nested values`.
  - **Body:** explains that a JSON object silently became `0.0` or `[]` and that `[{"id": 1}]` reached a library as `[0.0]`, the wider `AnyType`, the stricter tuples, keys and booleans, that a union tries its other types, the unions of `validate_types` on Python 3.12 and 3.13, and that the tests of RobotCode's copy moved here.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that CI and the docs workflow pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`, sync its delta specs into a new `openspec/specs/json-conversion` and into `openspec/specs/client` and `openspec/specs/server`, and commit the archive as its own signed commit: `docs(openspec): archive fix-json-helpers`.
- In `playground/anforderungen-und-ideen.md`, set TEST-3, JSON-1, JSON-3, JSON-4 and JSON-6 to done, and reduce PROTO-3 to `__all__`, `__version__` and `from_value`.
