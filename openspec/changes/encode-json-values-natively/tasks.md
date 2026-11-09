# Tasks

Every new test is run against a copy of the package without the part of the change that it covers, and must fail there. The task names that copy. A copy on `PYTHONPATH` wins over the editable install, also for the server processes that the tests start. Robot suites that pin behavior that stays pass before and after; they run in the integration checks.

The unit tests of the value format use the types of a module of their own, `tests/value_types.py`: a dataclass `Point(x: int, y: int)`, a named tuple `Pair`, an enum `Color` with the member `RED = "red"`, and a dataclass `Inner` inside a class `Outer`. Since `tests/` is on the module search path of pytest, their names are `value_types.Point` and so on.

## 1. The value format in the protocol package

- [ ] 1.1 In `packages/jsonrpcpeer/src/jsonrpcpeer/json_helpers.py`, pass `allow_nan=False` to `json.dumps` in `as_json` (design decision 1). In `tests/test_json_helpers.py`, add `test_as_json_fails_for_floats_that_json_does_not_allow`, parametrized over `nan`, `inf` and `-inf`, on its own, in a list and in a dataclass: it fails with a `ValueError`. In `tests/test_peer.py`, add `test_result_with_nan_is_answered_with_an_internal_error`, next to `test_result_that_cannot_be_written_is_answered_and_logged`: a handler that returns `{"value": float("nan")}` gets `-32603` and its `id`, and no message on the wire holds `NaN`. Verify that both tests fail in a copy of `jsonrpcpeer` without `allow_nan=False`. No Robot test: keyword values never reach `as_json` with `NaN` after group 2, since the value format encodes them; the round trips of `NaN` are Robot tests of 2.4 and 3.6.
- [ ] 1.2 Add `packages/protocol/src/robot_jsonrpcremote_protocol/values.py` with `ValueFormat`, `ValueCannotTravelError` and `ValueDoesNotFitError` (design decisions 1, 2 and 7): plain JSON with further dict types and `null` as `None`; with pickles, values whose place does not fix their type pickled as a whole with the agreed protocol, unpickled only at the top level; the markers; and the `TypeError` for values that may not travel and for a pickle without the agreement. Re-export them from the package's `__init__.py`. In the new `tests/test_protocol_values.py`, add:
  - `test_json_values_travel_as_plain_json`, with and without pickles;
  - `test_a_further_dict_type_comes_back_as_a_plain_dict`, with a dict subclass standing for `DotDict`;
  - `test_null_is_none_for_a_declared_type`;
  - `test_a_value_without_a_declared_type_is_pickled_with_the_agreed_protocol`, which checks the protocol in the pickle for 4 and 5;
  - `test_a_list_that_holds_a_tuple_is_one_pickle`;
  - `test_subclasses_of_the_json_types_are_pickled_and_keep_their_type`, for an `IntEnum`, an `OrderedDict` and a `str` subclass;
  - `test_nan_without_a_declared_type_is_a_pickle`;
  - `test_a_value_that_cannot_be_pickled_names_it`, for a lambda;
  - `test_a_dict_with_a_marker_key_is_pickled` and `test_a_dict_with_a_marker_key_cannot_travel_without_pickles`;
  - `test_an_object_of_an_unsupported_class_cannot_travel_without_pickles`, `test_other_subclasses_of_the_json_types_cannot_travel_without_pickles` and `test_a_pickle_without_the_agreement_is_not_unpickled`; for the last one, the pickle names a module that does not exist, and the error is a `TypeError`, not a `ModuleNotFoundError`.

  Remove the tests of `value_to_jsonable` and `jsonable_to_value` from `tests/test_json_helpers.py`; the new tests replace them. No Robot test: client and server use the value format only from group 2 on, whose Robot tests are those of 2.4 and 3.5. Verify the failures in copies of the protocol package that pickle a list of plain JSON, that pickle with the highest protocol instead of the agreed one, that let a dict with a marker key through as plain JSON, and that unpickle without the agreement.
- [ ] 1.3 Add the typed values to `values.py` (design decisions 2, 3 and 4): the forms for a declared type, with and without pickles; a value that is not of its declared type taking the path of an undeclared one; `__type__` for undeclared values without pickles, also inside lists; `type_name()` and `resolve_type_name()`; building only the supported kinds; and `ValueDoesNotFitError`. In `tests/test_protocol_values.py`, add:
  - `test_a_declared_dataclass_travels_as_its_fields`, `test_a_declared_named_tuple_and_enum_travel_in_their_forms`, `test_declared_built_in_values_travel_in_their_forms` and `test_declared_standard_types_travel_in_their_forms`, each with the values and forms of its scenario, which decode back to equal values of the same types; sets compare as sets;
  - `test_declared_values_inside_lists_and_dicts` and `test_a_declared_enum_travels_as_its_name_with_pickles`;
  - `test_a_value_that_is_not_of_its_declared_type_travels_as_without_one` and `test_decoding_a_form_that_does_not_fit_its_declared_type_fails`, for `"abc"` and `datetime`;
  - `test_an_undeclared_dataclass_names_its_type`, `test_undeclared_built_in_and_standard_values_name_their_type`, for `Any` and `int | datetime`, `test_a_union_with_none_declares_the_type` and `test_undeclared_typed_values_inside_a_list`;
  - `test_a_nested_class_is_named_with_its_qualified_name` and `test_a_standard_type_is_named_as_by_robot_framework`;
  - `test_decoding_a_name_of_something_else_fails`, for `os.path.join`, and `test_decoding_a_class_that_is_not_supported_fails`, for `collections.defaultdict`;
  - `test_decoding_a_dataclass_with_a_missing_field_fails` and `test_decoding_a_class_that_is_not_installed_fails`, whose texts name the type and the field or the module.

  No Robot test, for the reason of 1.2. Verify the failures in copies that pickle declared values when pickles are agreed, that write no `__type__` for undeclared values, that name a nested class by `__name__`, that build any class from `__type__`, and that ignore missing fields.

## 2. The agreement on pickles

- [ ] 2.1 In `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py`, add `pickle_protocol: int | None = None` to `ClientCapabilities` and `ServerCapabilities`, and a function that gives the agreed protocol from the two (design decision 5). In `tests/test_protocol_values.py`, add `test_pickles_are_agreed_with_the_lower_protocol` and `test_no_pickles_are_agreed_when_one_side_states_none`. No Robot test of its own: the Robot tests of 2.4 observe the agreement through client and server. Verify that they fail in a copy that takes the higher protocol, and in one that agrees on pickles when one side states none.
- [ ] 2.2 In `src/JsonRpcRemote/__init__.py`, add `rpc_pickles: bool = True`, which is not forwarded to the remote library. State `pickle.HIGHEST_PROTOCOL` in `initialize` unless it is false, keep a `ValueFormat` per `_Session` with `DotDict` as a further dict type, and use it for the arguments and the result of `run_keyword`, still without declared types. Word the failures as design decision 7 gives them. Give `tests/fake_server.py` an attribute `pickle_protocol` for its answer to `initialize`, and keep the raw params of the calls it gets. In a new `tests/test_client_values.py`, add:
  - `test_the_client_states_the_highest_pickle_protocol` and `test_rpc_pickles_false_states_no_pickle_protocol`;
  - `test_rpc_pickles_is_not_forwarded`, with a named init argument next to it;
  - `test_lists_and_dicts_reach_the_server_as_plain_json`, with a `DotDict`;
  - `test_a_tuple_is_pickled_when_pickles_are_agreed`;
  - `test_an_argument_that_needs_a_pickle_fails_before_it_is_sent`, against a fake server without `pickle_protocol`: the `TypeError` names the argument, the class and that the server reads no pickles, and the fake server gets no call;
  - `test_with_rpc_pickles_false_the_failure_names_the_option`;
  - `test_a_pickle_from_the_server_without_the_agreement_fails`, with `rpc_pickles=False`: a `TypeError`, and the pickle is not unpickled;
  - `test_a_typed_value_without_a_declared_type_comes_back_as_its_class`, for `{"__type__": "value_types.Point", "x": 1, "y": 2}` from the fake server.

  Verify the failures in copies of the client that state no protocol, that ignore `rpc_pickles`, that send without the `DotDict` type, and that unpickle without the agreement.
- [ ] 2.3 In `packages/server/src/robot_jsonrpcremote_server/`, add `--pickles`/`--no-pickles` with `ROBOT_JSONRPC_PICKLES` to `__main__.py` (design decision 8). Let each `RobotServerEndpoint` state the protocol in `initialize`, keep the `ValueFormat` that it agreed with its client, and pass it to the runner for the arguments and the return value, still without declared types. Answer a pickle without the agreement with `-32602`, and a return value that cannot travel with `-32603` and the `TypeError` text of design decision 7. Add:
  - in `tests/test_server_cli.py`, next to the tests of `ROBOT_JSONRPC_PORT`: `test_pickles_turned_off_from_the_environment`, for `no`; `test_command_line_takes_precedence_for_pickles`, for `off` and `--pickles`; and `test_pickles_value_from_the_environment_that_is_no_truth_value_is_a_usage_error`, for `maybe`, with exit code 2, without a traceback, and a message that names the variable and the value;
  - in `tests/test_endpoint.py`: `test_initialize_states_the_pickle_protocol`, with and without `--no-pickles`; `test_pickles_go_only_to_a_client_that_reads_them`, with two clients; `test_a_pickle_argument_without_the_agreement_is_refused`, with `-32602` and the keyword not run; `test_a_return_value_that_cannot_travel_to_a_client_without_pickles_is_an_error`; and `test_a_return_value_that_cannot_travel_from_a_server_without_pickles_names_the_option`.

  Verify the failures in copies of the server that read the variable as any non-empty text, that state the protocol with `--no-pickles`, that use one agreement for all clients, and that unpickle without the agreement.
- [ ] 2.4 Add Robot tests of the agreement:
  - **`atests/stdio_node_server.robot`**, against the Node server, which states no `pickle_protocol` as a server in another language does:
    - `Lists And Dicts Reach A Server In Another Language As JSON`: `Echo` of `[1, 2]` and of a dict from `&{dict}` returns them;
    - `A Tuple Comes Back Through A Server In Another Language`: `Echo` of `(1, "a")` returns that tuple, which travels with `__type__`;
    - `An Object That Needs A Pickle Fails Before It Is Sent`: an instance of `ArgumentValuesLib.Thing` fails with a `TypeError` that says that the server reads no pickles.
  - **A new suite `atests/value_format.robot`**: each test starts the server that it needs and stops it in its teardown, our server with `ArgumentValuesLib` on port 8288 with pickles, or on port 8289 with `--no-pickles`, and imports `JsonRpcRemote` itself, with `rpc_scope=TEST`. Its tests:
    - `With Pickles Turned Off On The Client An Object Fails With The Option`: imported with `rpc_pickles=no`, as a suite writes it, `Same Value` of a `Thing` names `rpc_pickles`;
    - `With Pickles Turned Off On The Server A Returned Object Fails With The Option`: `Make Thing` names `--no-pickles`;
    - `A Tuple Makes A Round Trip Without Pickles`, on either side.

  `atests/pickled_values.robot` stays as it is and keeps passing: with pickles, values of `Any` travel as pickles. A pickle without the agreement on the server is covered by the unit test of 2.3 only: our client never sends one. Verify the failures with the copies of 2.2 and 2.3.
- [ ] 2.5 Update the documentation for the agreement:
  - `docs/src/content/docs/reference/protocol.mdx`, section Values: lists and dicts of JSON values as plain JSON; pickles only by the agreement, as a whole, with the lower protocol; the markers; and the field `pickle_protocol` in the description of `ClientCapabilities` and `ServerCapabilities`;
  - `docs/src/content/docs/reference/server.mdx`: `--pickles`/`--no-pickles` in the table of options, and `ROBOT_JSONRPC_PICKLES` with its truth values in the table of environment variables;
  - `docs/src/content/docs/reference/library.mdx`: `rpc_pickles`;
  - `docs/src/content/docs/guides/transports.mdx`, where it says that the Python implementation sends Python objects as pickles: name the two options;
  - `docs/src/content/docs/roadmap.mdx`: plain JSON for lists and dicts and the agreement on pickles under Available.

  Verify the pages against the behavior of 2.2 to 2.4.

## 3. Typed values in the library definition, the client and the server

- [ ] 3.1 Add `return_type: str | None = None` to `KeywordDefinition`. In `packages/server/src/robot_jsonrpcremote_server/_runner.py`, write the argument types and the return type with `type_name()`, by walking Robot Framework's `TypeInfo` (design decision 4). Add to `tests/test_server_end_to_end.py`:
  - `test_the_definition_names_classes_with_their_module`, for `color: Color` and `at: list[Point] | None` of a test library with its types in a module of its own;
  - `test_the_definition_gives_the_return_type` and `test_a_keyword_without_a_return_type_has_none`;
  - `test_the_definition_names_standard_types_as_robot_framework_does`, for `datetime`.

  In `atests/server_only_library.robot`, Libdoc now shows the default as `button: ServerOnlyLib.Button = LEFT`, since the client cannot import `ServerOnlyLib`: change the expected text, which covers the modified scenario of the client spec. Update the unit tests of the client that expect a short type name the same way. Verify that the new tests fail in a copy of the server that writes `str(arg.type)` and no return type.
- [ ] 3.2 In `src/JsonRpcRemote/__init__.py`, resolve the type texts of the definition with `TypeInfo.from_string()` and `resolve_type_name()` once per definition, and give Robot Framework the resolved hints in `get_keyword_types()`, or the text where a leaf does not resolve (design decision 4). Add `python-path = ["atests"]` to `robot.toml`, so that the client can import the types of the Robot tests by their names. In `tests/test_client_values.py`, add `test_get_keyword_types_gives_the_installed_classes`, for `value_types.Color` and `list[value_types.Point] | None`, and `test_a_type_that_does_not_resolve_stays_a_text`, for `notinstalled.Point`. Verify the failures in a copy of the client that passes the texts through.
- [ ] 3.3 In the client, encode the arguments by the declared types of their `ArgumentDefinition`s and decode the result by `return_type` (design decision 6). Word a failed decoding of the result as `Return value got value ...` (design decision 7). In `tests/test_client_values.py`, add:
  - `test_an_enum_converted_by_robot_framework_reaches_the_server_as_its_name`: `red` in a Robot call, `"RED"` in the raw params;
  - `test_a_declared_return_value_becomes_its_class`, for `{"x": 1, "y": 2}` and `return_type` `value_types.Point` from a fake server without `pickle_protocol`;
  - `test_a_declared_enum_argument_goes_as_its_name_with_pickles`;
  - `test_a_return_value_of_a_class_that_is_not_installed_fails` and `test_a_return_value_that_does_not_fit_its_type_fails`, whose `ValueError` texts name the return value, the type and the module or the field `y`.

  Verify the failures in copies of the client that send without declared types and that decode the result without `return_type`.
- [ ] 3.4 In `_runner.py`, decode each argument by the keyword's `ArgumentSpec` before `running.Keyword` is built, hand a plain value to Robot Framework where its converter applies and decoding fails, and refuse the rest with `-32602` (design decision 6). Encode the return value by the declared return type. Add to `tests/test_server_end_to_end.py`:
  - `test_a_dataclass_argument_becomes_its_class`;
  - `test_an_enum_name_is_converted_as_by_a_local_library`, for `"red"`;
  - `test_an_enum_name_that_is_no_member_fails_with_robot_frameworks_message`, for `"BLUE"`, as a keyword error;
  - `test_a_dataclass_form_that_does_not_fit_is_refused`, with `-32602`, a message of the form `Argument 'at' got value ... that cannot be converted to ...` that names the field `y`, and the keyword not run;
  - `test_a_declared_return_value_travels_in_its_form_without_pickles`;
  - `test_a_return_value_without_a_declared_type_is_tagged_or_pickled_by_client`, with two clients.

  Verify the failures in copies of the server that leave all arguments to Robot Framework, that refuse a plain value that Robot Framework would convert, and that encode the return value without its declared type.
- [ ] 3.5 Add `atests/typed_values_types.py`, with a dataclass `Point`, a named tuple `Pair` and an enum `Color`, and `atests/TypedValuesLib.py`, with keywords that take and return them with declared types, keywords with `Any`, and a keyword `Describe` that returns the type name and the `repr` of what it got. Add `atests/_server_only/ServerOnlyTypes.py`, with a dataclass that only the server has, and a keyword of `TypedValuesLib` that returns it without a declared type. In the suite `atests/value_format.robot` of 2.4, whose tests start our server with `TypedValuesLib` too, with the folder `_server_only` on its module search path, add these tests:
  - `Declared Values Make A Round Trip With Pickles`, `... With Pickles Turned Off On The Client` and `... With Pickles Turned Off On The Server`: a `Point`, a `Pair`, a member of `Color`, a `datetime`, a `Decimal`, `bytes`, a `UUID`, a `Path`, a tuple, a set, a dict with integer keys and `NaN` come back equal and of their types, and `Describe` shows that the server got them as their types;
  - `Undeclared Values Make A Round Trip Without Pickles`, for the same values through the keywords with `Any`;
  - `A Dict From A Robot Variable Reaches The Server As A Dict`, for `&{dict}`;
  - `A Returned Class That The Client Does Not Have Fails`: without pickles, with a `ValueError` that names the class from `ServerOnlyTypes`;
  - `Libdoc Describes A Declared Enum With Its Members`, with `LibdocSpecs.py`.

  Verify the failures with the copies of 3.2 to 3.4.
- [ ] 3.6 Update the documentation for typed values:
  - `docs/src/content/docs/reference/protocol.mdx`: typed values, their forms, `__type__`, the names of types, and the field `return_type`, with the argument types written with modules;
  - `docs/src/content/docs/reference/library.mdx`: return values become their classes, and the classes must be installed on the client in the same modules as on the server;
  - `docs/src/content/docs/roadmap.mdx`: typed values under Available. Under Planned, "Servers in other languages" keeps the example servers in other languages and loses the conventions for values, which this change implements.

  Verify the pages against the behavior of 3.1 to 3.5.

## 4. The example server

- [ ] 4.1 In `examples/simple-robot-jsonrpcserver`, add `src/simple_robot_jsonrpcserver/shapes.py` with the dataclass `Point`, and a keyword `Move`, whose definition gives the argument types `simple_robot_jsonrpcserver.shapes.Point`, `int` and `int` and the same return type. It decodes and encodes with `ValueFormat(pickle_protocol=None)`, and its answer to `initialize` states no `pickle_protocol` (design decision 9). Add to `tests/test_example_server.py`:
  - `test_the_example_server_states_no_pickle_protocol`;
  - `test_move_returns_the_moved_point`, with a `Point` from the client.

  Add the Robot test `Move Returns The Moved Point` to `atests/stdio_own_server.robot`. Add a runnable example to `docs/examples/own-server` with a page command that `tests/test_docs_examples.py` runs. Describe `Move` and the types on the page Protocol, where it shows the example server, and in the README of the example. Verify that the tests fail in a copy of the example server that states a `pickle_protocol` and that returns the moved point as a plain dict.

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy`, and verify that they pass.
- [ ] 5.2 Run `uv run --all-packages pytest` and `uv run --all-packages robotcode run`, and verify that all unit tests and all Robot suites pass, `atests/pickled_values.robot`, `atests/argument_values.robot`, `atests/typed_init.robot` and `atests/libdoc.robot` included. Run the changed and new suites with Robot Framework 7.2 too.
- [ ] 5.3 Run `npm run build` in `docs/` and `uv run --all-packages pytest tests/test_docs_examples.py`, and verify that the site builds without broken links and that the examples run.

## Workflow follow-up

- The plan is committed as `docs(openspec): plan encode-json-values-natively`.
- After the implementation, check CI, including the Windows and the minimum Robot Framework jobs, then archive the change.
