# Proposal

## Why

The README says that a server that offers keywords can be written in any language, and that with a JSON-RPC library this takes only a few lines of code. The only example of a server is in Python, and the roadmap lists example servers in other languages as planned. Since `encode-json-values-natively`, values travel as plain and typed JSON to a server that reads no pickles, so a server in another language now gets lists and objects as well. Node.js comes first, because its JSON-RPC library `vscode-jsonrpc` speaks the framing of the Language Server Protocol, which the protocol uses. An example in Rust follows as a change of its own.

## What Changes

- **A new example server in Node.js** in `examples/node-robot-jsonrpcserver/`:
  - It is written in TypeScript, which Node.js runs directly, without a build step.
  - It uses `vscode-jsonrpc` for the framing, the requests, the notifications and the errors.
  - It serves a library of a few keywords that show what a server does: a result, a log message while the keyword runs, a list as an argument with a declared type, and a failure.
  - It serves a whole session, from `robot/initialize` to `robot/exit`, and states no pickle protocol.
  - It answers a call before the handshake and an unknown keyword with the codes of the reference server.
- **Transports, as in the Python example:**
  - TCP on `127.0.0.1:8271` by default, with `--port` to choose another port.
  - `--stdio`, for a `stdio:` URI.
  - `--pipe <address>`, also as `--pipe=<address>`, for a `pipe:` URI.
- **Its own README,** with how to install it with `npm ci` and how to start it, and **a check of its types** with `tsc` in CI.
- **The test server `atests/libraries/node_keywords.js` stays:** it tests the client against a server without a library, with the values as they arrive on the wire.
- **CI:** the test jobs install a Node.js version that runs TypeScript, and run `npm ci` in the example folder; the lint job checks the types of the example.
- **The uv workspace** excludes the folder, which has no `pyproject.toml`.
- **Docs:**
  - The protocol page gets a section on the example in Node.js, with its code and a runnable example in `docs/examples/node-server/`.
  - The roadmap lists the example as available and keeps Rust, Java and .NET as planned.
  - `AGENTS.md` and `CONTRIBUTING.md` name the folder and how to install it.
- **Not in this change:** the example in Rust, and changes to the client, the server or the protocol.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `protocol`: a new requirement that a server in Node.js can serve the protocol with a JSON-RPC library, shown by the example.

## Impact

- **Example:** new `examples/node-robot-jsonrpcserver/` with `package.json`, `package-lock.json`, `tsconfig.json`, `src/` and `README.md`.
- **Configuration:**
  - `pyproject.toml`: `exclude` in `[tool.uv.workspace]`.
  - `.gitignore`: the `node_modules` of the example.
  - `.github/workflows/ci.yml`: Node.js, `npm ci`, the type check.
- **Tests:**
  - New `tests/examples/test_node_example_server.py`, with the shared helper `tests/node_example.py`.
  - New Robot suites `atests/stdio/node_example.robot` and `atests/pipe/node_example.robot`, with commands in `atests/resources/stdio_vars.py` and `pipe_vars.py`, and the path of the example in `atests/resources/paths.py`.
  - `tests/docs/test_docs_examples.py` runs the new docs example.
- **Docs:** `docs/src/content/docs/reference/protocol.mdx`, `roadmap.mdx`, new `docs/examples/node-server/`, `AGENTS.md` and `CONTRIBUTING.md`.
- **Dependencies:** `vscode-jsonrpc` at runtime and `typescript` and `@types/node` for the type check, all for the example only; nothing changes for the Python packages.
