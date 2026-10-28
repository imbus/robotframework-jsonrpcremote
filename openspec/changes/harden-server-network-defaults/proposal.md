# Proposal

## Why

The server trusts everyone who can reach its address, and its defaults and docs make that easy to get wrong:

- **Open listener:** anyone who can connect can import the allowed libraries and run their keywords. Values travel as pickles, so a malicious client can also execute code on the server. The default bind address is `127.0.0.1`, but the first example in the server README binds to `0.0.0.0`, and binding to a network address logs no warning.
- **Unlimited message size:** the server creates each connection's peer without `max_message_size`, so a client can announce an arbitrarily large `Content-Length` and make the server buffer that much data.
- **Invalid port from the environment:** `ROBOT_JSONRPC_PORT=abc` ends the server with a `ValueError` traceback while the command line is parsed, instead of a usage error.

Authentication and encryption are out of scope here. Together with the hardening of pickle, TLS and Unix domain sockets, they need a design of their own.

Found in the project review of 2026-10-27 (items SEC-2 and SERVER-2).

## What Changes

- **Warning:** when the server listens on an address other than loopback, it logs a warning that every client that can reach the address can run keywords of the allowed libraries and, through pickled values, execute code on the server.
- **Message size limit:** incoming messages are limited to a default maximum size, and a CLI option changes the limit. A larger message closes the connection, as the peer already does when a limit is set.
- **Port from the environment:** an invalid `ROBOT_JSONRPC_PORT` fails with a usage error, like an invalid `--port`.
- **Docs:** the server pages of the documentation site show binding to a network address together with the warning, and a short security note explains what a client that can connect is able to do.

Assumptions recorded for review:

- The default limit is large enough for typical payloads such as screenshots; the design proposes the value.
- The warning does not stop the server from starting.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `server`: adds requirements for the warning on non-loopback addresses, for the default limit on incoming messages, and for an invalid port from the environment.

## Impact

- **Code:** `packages/server/src/robot_jsonrpcremote_server/__main__.py` (argument parsing, start of the TCP server, `handle_client()`).
- **CLI:** a new option for the message size limit.
- **BREAKING** for setups that send messages above the default limit; they need the new option.
- **Docs:** the server pages of the documentation site (options, security note).
- **Order:** independent of the other changes.
