# Proposal

## Why

Robot Framework on the client resolves the arguments of a keyword call and of a library import, and the client sends the finished values. The server gives them to Robot Framework on its side as if they came from a suite file, so Robot resolves them a second time. A local library gets the same values unchanged.

- **Strings change without any error.** The Windows path `C:\temp\new` reaches the keyword as `C:<TAB>emp<LF>ew`, the regular expression `\d+` as `d+`, and `end\` as `end`. Such strings are everyday values.
- **Text that looks like a variable fails, or is replaced on the server.** An escaped `\${amount}` in a suite, or the same text read from a file, fails with `Variable '${amount}' not found.` `%{PATH}` turns into the environment variable of the server, and `${{1+1}}` runs as Python on the server and arrives as `2`.
- **The same holds for everything else the client sends.** Named values and the names of named arguments change in the same way. In a library import, `\${amount}` makes the import fail, and a positional `key\=value` turns into a named argument. A library path with a backslash, as on Windows, or with `${...}` cannot be imported.
- **Keywords with embedded arguments never work.** `Embedded hello In The Name` fails with `Variable '${value}' not found.` Robot's dynamic API gives the client the name with the placeholder and the value as an argument, and the client sends both. The server then reads `${value}` from the name as one more value. If the pattern of another keyword fits that name too, the call fails with `Multiple keywords named ...`.

Found in the review of `add-documentation-site` on 2026-10-30 (item SERVER-14) and in the probes for `add-robot-integration-tests` on 2026-11-03 (item SERVER-22). The changes after this one test and rework this code, so the fix comes first.

## What Changes

- **Values arrive unchanged:** the server keeps Robot Framework from resolving what a client sends: strings as positional and named values and the names of named arguments, in keyword calls and in library imports. Lists, dicts and other objects were never affected, because Robot does not look into them.
- **Library names arrive unchanged:** a library path with a backslash or with `${...}` can be imported.
- **Control words keep working:** `AND`, `ELSE`, `ELSE IF`, `AS` and `WITH NAME` reach the library as they are, so that keywords such as `Run Keywords` and `Run Keyword If` still find them.
- **Embedded arguments work:** a keyword with embedded arguments is called by the name from its definition, with its values as arguments. A name with the values filled in is not a name from the definition and is answered with `KEYWORD_NOT_FOUND`.
- **Tests:** unit tests against the real server, and a Robot suite that compares each case with a local library.
- **Docs:** the protocol page says that values are final and how to call a keyword with embedded arguments; the pages on the arguments of a library and on the server say what a library gets; the roadmap lists embedded arguments.

Assumptions recorded for review:

- No client sends a name with the values filled in. The client of this project cannot, because Robot's dynamic API gives it only the name from the definition, and the protocol page already asks for that name. `test_keyword_name_with_several_matches_names_the_library` pins today's answer to such a name and changes with this fix.
- Named values of a library import that are not strings stay text unless a type hint converts them, as the page on the arguments of a library says. Keeping their type needs `robot.running.model.Argument`, which Robot Framework calls a temporary API that may go in 8.0, and it is a different defect. It goes into the backlog.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds requirements that values and library names from a client arrive unchanged, that control words keep working, and that a keyword with embedded arguments is called by the name from its definition.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/_runner.py` (`_robot_import_library`, `_robot_run_keyword`), `_endpoint.py` (`import_library`, which no longer builds Robot's `name=value` entries).
- **Protocol:** the messages stay the same. The protocol page states what the reference server already expects from `name` and adds that values are final.
- **Client:** no code change.
- **Tests:** `tests/test_server_end_to_end.py`, `tests/test_endpoint.py`, `tests/test_runner.py`, and new suites in `atests/`. The suite that needs a server without an allowlist takes port 8283.
- **Order:** after `add-server-runner-tests`, whose tests guard this code; before `add-robot-integration-tests`, whose tests then need no skips, and `fix-server-library-import`, which reworks the same import path.
