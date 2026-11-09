# Tasks

Every new test is run once against the code without the part of the change it covers, and must fail there.

- **Time limits:** a server that never connects can hang a test, so these checks and all runs on the Windows test VM have a hard time limit.
- **The VM:** Daniel starts it. When a task needs it, ask him and wait.
- **Bytecode:** copy no `__pycache__` to the VM.

## 1. The list in the client

- [x] 1.1 In `src/JsonRpcRemote/__init__.py`, add `_uri_from_list()` and call it in `JsonRpcRemote.__init__` before anything uses `self._uri`. Annotate `uri: list[str] | str` (design decisions 1 to 4).
  - Verify in `tests/test_client_connection.py`, against the helper:
    - **Requirement The command of a pipe or stdio URI can be a list:** both forms, the scheme as an element of its own and in front of the program, without regard to case; `stdio:`; an element that is a `pathlib.Path` and one that is a number become strings.
    - **Requirement A list URI is named as the string that it stands for:** An argument that needs quotes, where the string form of a list with `my library` quotes it, and `_split_command()` of that string gives the same command. The same for a program that starts with `//`, whose string form must not name a pipe.
    - **Requirement A list without a command is refused:** all four scenarios, with `pipe://robot`, `stdio://robot-jsonrpcremote-server` and `tcp://127.0.0.1:8271` for A URI with two slashes. Each test also checks, with a fake for `_Session.start`, that no session starts.
  - Counter-checks:
    - Without the check for `//`, A URI with two slashes must fail.
    - Without `str()` for the elements, the test with `pathlib.Path` must fail.
    - Without the quotes for a program that starts with `//`, its string form must fail.
- [x] 1.2 Verify that the list reaches the start of the server as its arguments, element by element (design decision 3), in `tests/test_client_connection.py`:
  - **Fakes for `create_pipe_subprocess()` and `create_stdio_subprocess()`** record the arguments, as in `test_a_command_is_split_as_its_platform_writes_paths`. The command holds the awkward arguments of the probe in the design: spaces, quotes, backslashes, an empty argument and a newline. `sys.platform` is patched to `win32` and to `linux`, and the recorded arguments must equal the command of the list. This covers An argument with a space, a quote or a backslash, and both forms and A stdio command as a list at the level of the start.
  - **A real start of `tests/minimal_pipe_server.py`** from a list, copied into a folder with a space in its name, as in `test_a_stdio_command_with_a_space_in_its_path_reaches_the_server`, calls `Echo`.

  Counter-check: with the elements joined by spaces instead of `shlex.join()`, the test with the awkward arguments must fail.

## 2. Robot suites

- [x] 2.1 Add the list forms to the Robot suites, with the lists of arguments in `atests/pipe_vars.py` and `atests/stdio_vars.py`, built from the same parts as the commands there:
  - **`atests/pipe_echo.robot`:**
    - A Command As A List With The Scheme As An Element Of Its Own: `pipe:`, the list variable of the arguments, and `--port    ${8271}`, which pipe mode ignores and which shows the conversion of a number. `Echo` works.
    - A Command As A List With The Scheme In Front Of The Program.
    - A List Without A Command Is Refused: an empty list, `pipe:` alone, `pipe://robot`, `tcp://127.0.0.1:8271` and a program without a scheme. The import fails with the message of design decision 4.
    - A String That Looks Like A List Stays A String: the import of `['pipe:', 'server']` fails with the error for an unsupported scheme.
  - **`atests/stdio_echo.robot`:** A Command As A List, with `stdio:`.
  - **`atests/pipe_lost_connection.robot`:** A List URI In The Lost-Connection Error. It imports `ConnectionLossLib` from a list under an alias of its own; `Exit Server` fails with `Connection to 'pipe:…' was lost while running keyword 'Exit Server'` and the exit code 3.

  This covers every scenario of the three requirements from Robot Framework. Verify locally and on the VM.

  Counter-checks:
  - Against the client without the call of `_uri_from_list()`, the list tests must fail.
  - Against the annotation `str | list[str]`, the test with `${8271}` must fail.

## 3. Documentation

- [x] 3.1 Document the list:
  - **`docs/src/content/docs/guides/transports.mdx`:** a section "The command as a list" after the section on the server that the client starts. It shows the new example `docs/examples/pipe/greet_list.robot` and says that the elements are the arguments as they are, that it works for `stdio:` the same way, and that the scheme can also stand in front of the program (design decision 6).
  - **`docs/src/content/docs/reference/library.mdx`:** the row of `uri` names the list for `pipe:` and `stdio:`.
  - **`docs/src/content/docs/roadmap.mdx`:** the bullet of the client on starting a server names the list.
  - **`tests/test_docs_examples.py`:** `test_pipe` also runs `greet_list.robot`.

  Review the implementation of groups 1 and 2 against the pages. Verify with `uv run --all-packages pytest tests/test_docs_examples.py` on Linux and on the VM, and with `npm ci` and `npm run build` in `docs/`, which also checks the links.

## 4. Integration checks

- [x] 4.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform win32` and `uv run --all-packages pytest`; verify all pass.
- [x] 4.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"`; verify all Robot suites pass, the new list tests included.
- [x] 4.3 On the Windows test VM, run the unit tests and `robotcode run` with `uv sync --all-packages` and hard time limits, on Python 3.12 and 3.15. Verify that all pass, that the list tests ran, and that no process stays behind.
- [x] 4.4 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`). Stage only the paths of this change, because another session may work on `main`, and check the staged files before the commit.
  - **Subject:** `feat(client): take the command of a pipe: or stdio: URI as a list`.
  - **Body:** why a suite wants the list, the two forms, the string form in messages, and why the annotation is `list[str] | str`.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`. Check that CI and the docs workflow pass, and that the uploaded `output.xml` shows the list tests on `ubuntu-latest`, `macos-latest` and `windows-latest`. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive` and sync its delta spec into `openspec/specs/client`.
- In the backlog, mark CLIENT-20 as done.
