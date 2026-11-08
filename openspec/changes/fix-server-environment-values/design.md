# Design

## Context

`build_arg_parser()` reads the environment variables while it builds the parser and passes their values as the defaults of the options. For the port it converts the value with `int()` right there, so an invalid value raises before `parse_args()` runs, whatever the command line holds; `--help` fails, too. For the mode, the value from the environment becomes the default of `--mode`, whose `choices` argparse checks only for a value on the command line; `run()` then refuses every mode other than `tcp` and `stdio` with the message for the reserved mode `pipe`.

Checked with Python 3.12 and 3.14 on a small parser:

- argparse converts a default that is a string with the option's `type`, but only when the option is not given, and only after the command line has been read, so `--help` still works. An invalid value ends with the same error as on the command line, such as `argument --port: invalid int value: 'abc'`, and exit code 2.
- argparse does not check `choices` for a default. Its own message for an invalid choice differs between the versions: 3.12 lists the choices without quotes, 3.14 with quotes.

## Goals / Non-Goals

**Goals:**

- The same invalid value gives the same usage error, whether it comes from the command line or from the environment.

**Non-Goals:**

- `ROBOT_JSONRPC_BIND` and `ROBOT_JSONRPC_PIPE_NAME`: every string is a valid value for them at this point; an address that cannot be bound is a failed start, as on the command line.
- An empty value: it is checked like any other, so an empty `ROBOT_JSONRPC_PORT` is a usage error. Only `ROBOT_JSONRPC_BIND` treats it as unset, because it splits its value at commas.
- A port outside 0 to 65535: it is a failed start with exit code 1 today, from the command line and from the environment alike.

## Decisions

### 1. argparse converts the port from the environment

The default of `--port` becomes the string from `ROBOT_JSONRPC_PORT`, or `str(DEFAULT_PORT)` without it, so argparse converts it with `type=int`. An invalid value then gets exactly argparse's error for `--port abc`, a value on the command line wins without a check of its own, and `--help` works with any environment.

*Alternative considered:* check the variable in `run()` and name it in the error, such as `invalid ROBOT_JSONRPC_PORT 'abc'`. That would need a default of `None` and code of its own for what argparse already does. The error names `--port` and the value, and the help of `--port` names the variable, so the value can be found.

### 2. A `type` function checks the mode, for both sources

`--mode` gets a `type` function that returns a known mode and raises `argparse.ArgumentTypeError` for any other value, with the message `invalid choice: 'tpc' (choose from tcp, stdio, pipe)`. argparse calls it for a value on the command line and, as for the port, for the default from `ROBOT_JSONRPC_MODE`, and reports `argument --mode: ` with that message. Checked with Python 3.12 and 3.14: both sources give the same error in the same form on both versions, `--stdio` with an invalid `ROBOT_JSONRPC_MODE` takes the mode `stdio`, and `--help` works. `--mode` keeps its `choices`, which the help shows; the modes are one constant that the `choices` and the function share. `run()` then refuses only the mode `pipe`, with its message that it is not supported yet.

*Alternative considered:* keep the parser as it is and split the check in `run()` into an unknown and the reserved mode. The parser would then still accept an invalid mode from the environment, `run()` would have to write argparse's error by hand, and the error would differ from the one for `--mode tpc` on Python 3.14, which quotes the choices.

## Risks / Trade-offs

- [The error for a value from the environment names the option, not the variable] → The value in the error and the help of the option point to the variable; the server reference says that an invalid value in the environment gives the error of its option.
- [On Python 3.14, the error for `--mode tpc` no longer quotes the choices] → It is the same error on every version now; nothing reads its form.

## Migration Plan

None. Valid values keep working. An invalid value in the environment now ends with a usage error instead of a traceback, and it no longer matters when the option is given on the command line.
