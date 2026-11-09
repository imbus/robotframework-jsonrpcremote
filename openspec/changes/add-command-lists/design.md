# Design

## Context

See proposal.md for the motivation. The starting point in `src/JsonRpcRemote/__init__.py`:

- **`JsonRpcRemote.__init__`** takes `uri: str`, keeps it as `self._uri`, and starts the first session at the end of the import. Its messages name `self._uri`: the reconnect warning, the error of a changed library definition and the error of connect retry when it gives up.
- **`_Session`** gets the same string. `create_connection()` picks the transport by the scheme, `_create_pipe_connection()` and `_create_stdio_connection()` split the command with `_split_command()`, and the lost-connection errors name the string.
- **`_split_command()`** is `shlex` in POSIX mode without comments: on POSIX, the same as `shlex.split()`; on Windows, without an escape character, so that a backslash is ordinary and quotes still group an argument.
- **`clarify-global-library-scope`**, planned and not implemented, picks the end of its reconnect warning by the scheme of the URI.

**Probes** with a library whose `__init__` takes the annotated `uri`, on Robot Framework 7.2 and 7.5, with the same result on both:

| `uri` | `str \| list[str]` | `list[str] \| str` |
|---|---|---|
| `@{X}`, `pipe:` and a list of strings | the list | the list |
| a list with `${8271}` | the repr of the whole list, as a string | the list, with `'8271'` |
| the string `pipe:server --pythonpath . MyLibrary` | the string | the string |
| the string `['pipe:', 'looks like a list']` | the string | the string |
| an inline list, `${{['stdio:', 'server']}}` | the list | the list |

`_split_command(shlex.join(argv))` gave `argv` back for paths with spaces, single and double quotes, backslashes, an empty argument, `#`, `$`, `*`, `|`, `>`, a tab, a newline and umlauts, with the rules of both POSIX and Windows.

## Goals / Non-Goals

**Goals:**

- A list reaches the server as its arguments, element by element, on every platform.
- One path through the client for strings and lists: the session, its transports and every message stay as they are.

**Non-Goals:**

- Splitting the string form differently, or a new way to quote in it.
- Lists for the arguments of the remote library, which `*library_args` already takes.

## Decisions

### 1. Two forms of the list, the documentation shows one

- **The scheme as an element of its own:** a first element that is `pipe:` or `stdio:`, without regard to case, and nothing else. The command is the rest of the list. It combines with a list of arguments that a suite already has: `@{SERVER}    pipe:    @{SERVER ARGS}`.
- **The scheme in front of the program:** a first element that starts with `pipe:` or `stdio:` and goes on with the program, which is the rest of that element. It reads as the string form, split at its spaces.
- **Daniel chose to accept both,** with the documentation showing the scheme as an element of its own.
- **Alternatives:**
  - Only the scheme as an element: a list in the shape of the string form would fail, though nobody would expect it to.
  - Only the scheme in front of the program, as first sketched in the backlog: combining it with an existing list of arguments takes inline Python, such as `${{['pipe:' + $ARGS[0], *$ARGS[1:]]}}`.

### 2. `uri: list[str] | str`

- Robot Framework tries the types of a union in their order (probe):
  - With `str` first, a list that holds a number, such as `${8271}`, becomes the repr of the whole list. The client would then look for a program named after that repr.
  - With `list[str]` first, Robot Framework converts each element to a string, and a string stays a string, also one that looks like a Python list.
- The helper of decision 3 turns each element into a string with `str()` too, for a caller in Python that passes something else, such as a `pathlib.Path`.
- **Alternative:** `str | list[Any]` behaved the same in the probe, but `list[str]` states what the client takes.

### 3. A list becomes its string form at the import

- A new helper `_uri_from_list()` turns a list into the scheme in lower case, followed by `shlex.join()` of the command, so `pipe:` and `robot-jsonrpcremote-server`, `--pythonpath`, `.` and `MyLibrary` become `pipe:robot-jsonrpcremote-server --pythonpath . MyLibrary`. `JsonRpcRemote.__init__` calls it before anything uses `self._uri`, and keeps the result as `self._uri`.
- **The way back is exact:**
  - `shlex.join()` is documented as the inverse of `shlex.split()`, and `_split_command()` is `shlex.split()` on POSIX.
  - On Windows, `_split_command()` differs only in having no escape character. `shlex.join()` writes a backslash only inside single quotes, where POSIX mode has no escapes either.
  - The probe in the context confirms it with both rules.
  - **A program that starts with `//`,** such as `//server/share/tool.exe`, needs no quotes for `shlex.join()`. The string `pipe://server/share/tool.exe` would then name a pipe, so the helper quotes such a program itself: `pipe:'//server/share/tool.exe'`.
- **The result:**
  - The session, its transports, the split and every message work with the string as they do now.
  - The scheme check of `clarify-global-library-scope` sees `pipe:` or `stdio:` as for a string.
  - A user can copy the string from a message and use it as `uri`.
- **Alternative:** hand the list to the session and skip the split. That is a second path through `_Session` and both transports, and the messages would need a string all the same.

### 4. Refusing a list without a command

- The helper raises `ValueError` before `JsonRpcRemote.__init__` starts the session, so no process is started. Robot Framework reports it as the failed import of the library.
- **The message** names the form, with an example, and shows what the list held: "A list for uri must hold the command of a pipe: or stdio: URI, as in ['pipe:', 'robot-jsonrpcremote-server', 'MyLibrary'], not […]".
- **It is refused:**
  - an empty list;
  - a scheme without a program, as in `pipe:` alone;
  - a first element whose scheme is followed by `//`, such as `pipe://robot`, `stdio://…` or `tcp://…`;
  - a first element without the scheme `pipe:` or `stdio:`.
- A string `uri` keeps its checks in `create_connection()`, unchanged.

### 5. Tests

- **Unit tests** in `tests/test_client_connection.py`:
  - `_uri_from_list()` for both forms, `stdio:`, a `pathlib.Path` and every refusal.
  - The arguments that reach `create_pipe_subprocess()` and `create_stdio_subprocess()`, recorded by a fake, with the awkward arguments of the probe and with `sys.platform` patched to `win32` and `linux`.
  - A real start of `tests/minimal_pipe_server.py` from a list, from a folder with a space in its name, as in `test_a_stdio_command_with_a_space_in_its_path_reaches_the_server`.
- **Robot suites:**
  - `atests/pipe_echo.robot` imports our server with both forms. Its list is built from a list variable of `atests/pipe_vars.py` and holds `--port    ${8271}`, which pipe mode ignores and which shows the conversion of a number.
  - `atests/pipe_echo.robot` also gets the refusals of a list without a command.
  - `atests/stdio_echo.robot` gets one test with `stdio:`.
  - `atests/pipe_lost_connection.robot` gets a test with a list, for the URI in the lost-connection error.
- **Windows:** the test VM runs them, also with backslashes in the elements.

### 6. Documentation

- **Guide `guides/transports.mdx`:** a section "The command as a list" after the section on the server that the client starts. It has the example `docs/examples/pipe/greet_list.robot` and says:
  - the elements are the arguments as they are, without quoting and on Windows without a rule for backslashes;
  - it works for `stdio:` the same way;
  - the scheme can also stand in front of the program.
- **`reference/library.mdx`:** the row of `uri` names the list.
- **`roadmap.mdx`:** the client bullet on starting a server names the list.
- **`tests/test_docs_examples.py`:** `test_pipe` also runs `greet_list.robot`.

## Risks / Trade-offs

- [The string in messages quotes as a POSIX shell does, also on Windows] → It is only for reading, and the same string as `uri` starts the server on Windows too (probe).
- [Two forms for the same list] → The documentation shows one. The other exists so that a list in the shape of the string form does not fail.
- [Robot Framework could change how it converts unions] → The probe runs on 7.2 and 7.5. The Robot test with `${8271}` runs on every version in CI, also on the minimum.
