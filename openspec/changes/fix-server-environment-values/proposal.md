# Proposal

## Why

The environment variables `ROBOT_JSONRPC_PORT` and `ROBOT_JSONRPC_MODE` set the defaults of `--port` and `--mode`, but an invalid value in them is not handled like the same value on the command line:

- **Port:** `ROBOT_JSONRPC_PORT=abc` ends the server with a `ValueError` traceback while the command line is parsed, before argparse checks anything. This happens even with `--port 9000` on the command line, although the server reference says that an option takes precedence over its environment variable.
- **Mode:** `ROBOT_JSONRPC_MODE=tpc` is refused with a usage error, but it says that the mode `tpc` is "not supported yet", which fits only the reserved mode `pipe`. On the command line, `--mode tpc` gets argparse's usual error for an invalid choice.

Found in the project review of 2026-10-27 (item SERVER-2). This change replaces the planned change `harden-server-network-defaults`, whose other parts were dropped: a warning for an address other than loopback would warn about the use the server is made for, and a default limit on the size of messages belongs to the design of access control.

## What Changes

- An invalid `ROBOT_JSONRPC_PORT` ends the server with a usage error that names `--port` and the value, as `--port abc` does, with exit code 2 and without a traceback.
- An unknown `ROBOT_JSONRPC_MODE` ends the server with a usage error that names `--mode` and the value and lists the modes, as `--mode tpc` does. Only the reserved mode `pipe` is still refused as not supported yet.
- A value on the command line takes precedence over an invalid value in the environment.
- The server reference says what an invalid value in the environment does.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds a requirement that an invalid value of an environment variable is a usage error, as the same value given to its option.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/__main__.py` (`build_arg_parser()` and the check of the mode in `run()`).
- **Tests:** `tests/test_server_cli.py`.
- **Docs:** the section on environment variables of the server reference.
- **Order:** independent of the other changes.
