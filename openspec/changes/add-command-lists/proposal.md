# Proposal

## Why

The `uri` argument of `JsonRpcRemote` is a string, and the client splits the command of a `pipe:` or `stdio:` URI as a POSIX shell does. A suite that keeps the command of its server as a list, as Robot Framework keeps lists of arguments, has to join it itself, for example with `${{shlex.join($ARGS)}}`, and has to put `pipe:` in front of the joined string: inside the first element, the quotes of `shlex.join()` would swallow the scheme as soon as the path of the program needs them. Passing the list itself does not work: `uri=pipe:${LIST}` gives the repr of the list, and `@{LIST}` spreads it over `uri`, `library_name` and the arguments of the remote library. This is backlog item CLIENT-20, from the review of `add-pipe-transport`.

## What Changes

- **`uri` also takes a list** for a `pipe:` or `stdio:` URI with a command, in two forms:
  - The scheme as an element of its own, followed by the program and its arguments, as in `@{SERVER}    pipe:    @{SERVER ARGS}`. This form combines with a list of arguments that a suite already has, and the documentation shows it.
  - The scheme in front of the program, as in the string form: `@{SERVER}    pipe:robot-jsonrpcremote-server    --pythonpath    .    MyLibrary`.
- **The elements are the arguments as they are:** the client neither splits nor unquotes them, and on Windows a backslash needs no rule. An element that is not a string, such as `${8271}`, becomes a string.
- **One way through the client:** at the import, the client turns the list into the string form, the scheme followed by the command as `shlex.join()` quotes it. From then on, it handles that string as a string URI: its messages name it, for example when a connection is lost, and the client splits it again when it starts the server, with the same arguments as in the list.
- **A list without a command is refused at the import,** with an error that says that a list holds the command of a `pipe:` or `stdio:` URI: an empty list, a list with the scheme alone, and a list whose first element is a URI with `//`, such as `tcp://…` or `pipe://…`, or has no supported scheme.
- **The type of `uri` becomes `list[str] | str`,** so that Robot Framework passes a list unchanged and converts its elements to strings.
- **Docs:** the guide Transports shows the list form, the reference of the library names it in the row of `uri`, and the roadmap lists it.
- **Not in this change:** a list for `tcp://` or `pipe://<name>`, which have no command, and lists on the side of the server.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `client`: a new requirement for the command of a `pipe:` or `stdio:` URI as a list.

## Impact

- **Client:** `JsonRpcRemote.__init__` and a new helper in `src/JsonRpcRemote/__init__.py`. The session and its transports keep working with the string.
- **Tests:** `tests/test_client_connection.py`, `atests/pipe_echo.robot`, `atests/stdio_echo.robot`, `atests/pipe_vars.py` and `atests/stdio_vars.py`.
- **Docs:** `docs/src/content/docs/guides/transports.mdx`, `reference/library.mdx` and `roadmap.mdx`; a new example `docs/examples/pipe/greet_list.robot`, which `tests/test_docs_examples.py` runs.
- **Compatibility:** a string URI behaves as before. `clarify-global-library-scope` picks the text of its reconnect warning by the scheme of the URI string, which a list URI has, too.
- **Order:** after `add-pipe-transport`. Independent of `clarify-global-library-scope`.
