# Design

## Context

See proposal.md for the motivation. What the code does today:

- **Defaults:** `_robot_import_library` builds every `ArgumentDefinition` with `value_to_jsonable(arg.default)`, which pickles every value that is not `null`, a string, a number or a boolean. On the client, `get_keyword_arguments` decodes it with `jsonable_to_value`. In the protocol, `ArgumentDefinition.default` has the type `AnyType | None`.
- **Name:** the server imports a library with its token as alias, and `LibraryDefinition.name` is `lib.name`, which is that alias. `lib.real_name` is the name without the alias; the answer `KEYWORD_NOT_FOUND` uses it already. The keyword store keys the library by the token, and `_robot_finalize_library` removes it by the token.
- **Disconnect:** when a client goes, the peer lets its running request handlers finish. `handle_client` then awaits `endpoint.finalize_all()`, which finalizes a copy of `_imported_tokens`, and calls `endpoint.cleanup()`. `import_library` adds its token only once the import has completed. All of this runs on the event loop; imports and finalizations run one after another on the runner thread.
- **Message cache:** `LOGGER` keeps every message of the framework in `_message_cache`, so that a logger registered later still gets the earlier messages: the console, the syslog, the output file, the listeners from the command line and other loggers. Only `rebot` turns the cache off; a `robot` run keeps it until the run ends. The hook loop of the server runs inside the first keyword of its run (`_HookListener.start_keyword`), when all these loggers are registered.

Checked on 2026-11-06 with Robot Framework 7.2 and 7.5: `ArgInfo.default_repr`, `TestLibrary.real_name` and `Logger.disable_message_cache` exist in both, and `default_repr` has the same code in both: the name for an `Enum` member, `safe_str` for everything else.

## Goals / Non-Goals

**Goals:**

- A library definition holds no pickle, in either direction.
- The fix for the disconnect stays in the endpoint; the peer, the runner and `handle_client` do not change.
- The protocol keeps its fields and their types.

**Non-Goals:**

- Stopping an import or a keyword whose client has gone: the runner thread finishes what it runs. That belongs to the planned keyword timeouts and cancellation.
- Return values whose class only the server has (the rest of CLIENT-12).
- The rest of the measured growth, about 6 % or 60 bytes per connection, which did not come from these messages.

## Decisions

### 1. A default is a JSON scalar of an exact type, or the text of `default_repr`

```python
def _default_of(arg: ArgInfo) -> SimpleType:
    value = arg.default
    if type(value) in (type(None), str, bool, int) or (type(value) is float and math.isfinite(value)):
        return value
    return arg.default_repr
```

- The exact type decides, not `isinstance`: `bool` is a subclass of `int`, and the members of an `IntEnum` or a `StrEnum` are numbers and strings. JSON would carry only their value, while Libdoc shows the name of the member, such as `RED`.
- `inf` and `nan` become text: Python's `json` writes them as `Infinity` and `NaN`, which is no JSON.
- `default_repr` is the text that Libdoc shows for a local library. The client hands it to Robot as a string, and Libdoc shows a string as it is. So Libdoc shows a remote library as it shows a local one; `atests/libdoc.robot` compares both for `LibdocLib`, whose defaults include a list, bytes and `None`.

Alternatives:

- **`repr()`:** differs from Libdoc, for example `<Button.LEFT: 1>` instead of `LEFT` and `b'ab'` instead of `ab`.
- **Pickles, and text only where pickling fails:** the client would still unpickle when it imports the library, which fails for a class that only the server has, and runs code from the server.
- **Only `has_default`, without the value:** Robot needs a default to treat an argument as optional, so the client would have to make one up, and Libdoc would show it.
- **Lists and dicts as JSON where they hold only JSON values:** a second rule for a value that the client does not use (decision 2). A tuple inside would already show differently in Libdoc.

### 2. The client hands the defaults to Robot unchanged

`get_keyword_arguments` returns `(name, arg.default)`. Robot on the client uses a default for three things:

- **Libdoc** shows it (decision 1).
- **Filling in a missing argument:** never, because the `run_keyword` of the client takes named arguments (see the assumptions in the proposal).
- **Converting an argument by the type of its default:** for a string default, Robot converts nothing (`# Don't convert arguments to strings.` in `ArgumentConverter`). So the client sends the string, and Robot on the server converts it by the real signature. Scalars convert on the client as before, and so does an argument whose type from the definition Robot knows.

The protocol type stays `AnyType | None`. The protocol is meant for servers in any language, and the client can hand any JSON value to Robot; a type of only scalars would make the client reject a definition with a list as a default. The protocol reference says what the reference server sends.

### 3. The definition carries `lib.real_name`, and the token stays the alias

`real_name` is the name that Robot gives the library without an alias: the name of the class or module, and for a path the file name without its extension (`PathLib`). The token stays the alias, because the keyword store keys each import by it, and finalizing removes the library by it.

On the client, `_definition_changes` compares the name too, and its message then reads `library attributes changed: name`. The fake server in `tests/fake_server.py` names the library as the import asked for it, as the real server will; today it uses the token.

### 4. An import that completes after the disconnect finalizes its library itself

`finalize_all()` first marks the endpoint as disconnected, and only then takes its copy of the tokens. `import_library` checks the mark as soon as the import has completed: if the mark is set, it finalizes the library at once instead of adding the token. Both run on the event loop, and there is no `await` between the check and adding the token. So `finalize_all` finalizes every token added before the mark, and `import_library` every later one. That includes an import that completes while `finalize_all` still waits for another library.

Both places finalize through one helper, which logs a failure at DEBUG, as `finalize_all` does today. Once the server has stopped its runner, a late finalization fails with "server is shutting down" and is only logged; the server ends, and the library with it. The answer to the late import goes to the closed connection and is lost, like every answer after a disconnect (`_write_answer`).

Alternatives:

- **`finalize_all` first waits until no request runs (`wait_idle`):** one line, but `cleanup()` would come only after the longest running keyword, and until then the endpoint would forward its log messages to the closed connection.
- **`finalize_all` repeats until no token is left:** misses the main case, in which the import completes after `finalize_all` has ended.
- **Cancelling the import:** the runner thread cannot stop an `__init__` that runs (Non-Goals).

### 5. The hook loop turns the message cache off

`LOGGER.disable_message_cache()` is the first step of `_hook_loop`. At that point Robot has registered every logger that the cache serves, and the server registers none later. `rebot` calls the same method once it has registered its console logger.

Alternatives:

- **In `run()`, before `suite.run()`:** the output file and the listeners, which `suite.run()` registers, would miss the messages logged before them.
- **Emptying the cache after each import:** needs the private list, while turning the cache off is one public method.

### 6. Tests

- **End to end** in `tests/test_server_end_to_end.py`, with the real server:
  - A library `DefaultsLib` holds the defaults of the scenarios. Its keywords return what they got as text, such as `list [3, 4]`, so that no return value needs a pickle. The default `nested` of `DescribedLib` now arrives as `"[1, {'a': 2}]"`, and its test no longer decodes the defaults.
  - The name: `EndToEndLib`, `PathLib` from a path, and two imports of one library.
  - The disconnect: a library `MarkedLib(marker, delay)` sleeps `delay` seconds in its `__init__`, and its listener writes a line into the file `marker` when the library is closed. Each test waits for the line with a time limit while the server goes on running, and then checks that there is exactly one. The import takes 1 s, and the client disconnects after 0.3 s. The scenario "Disconnect after the import" passes today already; it guards the reworked finalizing.
  - The message cache: a keyword of a library in the server counts the messages in `LOGGER._message_cache` that name `EndToEndLib`. After 100 sessions that import and finalize it, the count is 0; today it is above 100.
  - The conversion scenarios of the modified requirement pass today already. Their counter-check gives the argument a string as its default, which turns Robot's conversion off.
- **Endpoint unit tests** in `tests/test_endpoint.py`: a stub whose import and finalization wait for events that the test sets checks the order of decision 4 without depending on timing. It covers an import that completes after the disconnect, one that completes while another library is being finalized, and a late finalization that fails.
- **Client unit tests** with `tests/fake_server.py`: a pickle that names a missing module arrives unchanged as the default, and a definition that differs only in its name fails the reconnect.
- **Robot** in a new suite `atests/server_only_library.robot` on port 8286: the server gets `--pythonpath` to `atests/_server_only/`, from which the Robot run cannot import. Its library has `Click` with an `Enum` default and `Call` with `f=lambda: 1`. The suite calls both without the argument, calls `Click` with `RIGHT`, and checks that Libdoc shows `button: Button = LEFT`. Without the server part, the lambda fails the import, and the pickled `Enum` member costs `Click` on the client. The client part is covered by the unit test with the pickle, because the server no longer sends one.
- **Robot** in `atests/argument_values.robot`: a keyword whose defaults are a sentinel object gives the same as the local library when it is called without them. Only Robot Framework decides what the client sends, so a unit test that calls `run_keyword` directly cannot show it.

## Risks / Trade-offs

- **[A text default can hold a memory address]** → Accepted in the proposal; Libdoc shows the same for a local library.
- **[For a default that is no JSON scalar, the conversion moves to the server]** For a `date` default, the client sends the string, and Robot on the server converts it. → The library gets the same value. A value that cannot be converted fails the keyword on the server with Robot's message, which the server sends whole.
- **[The test of the message cache reads a private attribute of Robot]** → It reads `LOGGER._message_cache` directly, so a Robot version without it fails the test instead of passing it. CI runs Robot Framework 7.2 and the latest version.
- **[The disconnect tests depend on timing]** The client has to disconnect while the import runs. → The import takes 1 s, and the disconnect comes after 0.3 s. An import that starts late still runs after the disconnect, because the server has read the request before. A missing finalization fails the test at the time limit instead of hanging it.
- **[A late finalization runs after `cleanup()`]** → Its log messages go nowhere: `log_message` drops them once `cleanup()` has run, as every message after a disconnect.
