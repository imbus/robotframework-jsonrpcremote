# Design

## Context

See proposal.md for the motivation. The starting point:

- **The Python example** in `examples/simple-robot-jsonrpcserver/` serves `SimpleRobotLibrary` over TCP on `127.0.0.1:8271`, with `--stdio` and with `--pipe ADDRESS`. It refuses an import and a keyword call before the handshake with `-32000`, and an unknown keyword with `-32001` and the message `Keyword '<name>' not found in library '<library>'.` `tests/examples/test_example_server.py` tests it, the suites `atests/stdio/own_server.robot` and `atests/pipe/own_server.robot` run it, and the protocol page shows its code, with the runnable examples in `docs/examples/own-server/`.
- **The test server** `atests/libraries/node_keywords.js` is Node.js without a library. It speaks stdio and `--pipe=`, and the Node suites in `atests/stdio/` and `atests/pipe/` use it. They skip without `node`, except in CI.
- **Values:** since `encode-json-values-natively`, a side that states no `pickle_protocol` gets lists and objects as plain JSON, and typed values in their form or with `__type__`; see the protocol page, section Values.
- **The uv workspace** has the members `packages/*` and `examples/*`. A folder under `examples/` without a `pyproject.toml` stops uv with `Workspace member … is missing a pyproject.toml`. A probe with uv confirmed that `exclude` in `[tool.uv.workspace]` removes the error.
- **CI** installs no Node.js and uses that of the runner.

**Probe:** a TypeScript server with `vscode-jsonrpc` 10.0.0, `typescript` 7.0.2 and `@types/node` 26:
- **Running and checking:** Node.js 26 ran it directly, with ESM and named imports from `vscode-jsonrpc/node`. `tsc` checked it without errors.
- **Transports:** our client imported its library and called its keywords over stdio, with `StreamMessageReader` and `StreamMessageWriter` on stdin and stdout, and over a pipe, with `SocketMessageReader` and `SocketMessageWriter` on `net.connect()` to the address of `--pipe=`.
- **Values:** the list `[1, 2, 39]` for an argument declared as `list[int]` arrived as JSON, and the keyword returned `42`.

## Goals / Non-Goals

**Goals:**

- An example that a developer of another language can read from top to bottom and copy: the messages of the protocol as types, and a handler for each.
- The same transports and answers as the Python example, so that the protocol page can describe both in the same terms.

**Non-Goals:**

- A package to install from npm, or a library for servers in Node.js.
- Replacing the test server `node_keywords.js` (decided by Daniel, 2026-11-10).

## Decisions

### 1. `vscode-jsonrpc`

- `createMessageConnection()` with a reader and a writer gives the framing with `Content-Length`, the dispatch of requests and notifications, `ResponseError` for errors with a code, and `-32601` for an unknown method.
- Its framing is that of the Language Server Protocol, which the protocol uses.
- **Daniel chose it,** after a comparison on 2026-11-10:
  - `json-rpc-2.0` works with any transport and has no dependencies, but has no framing.
  - `jayson` and `jaysonic` speak over HTTP and TCP without the framing.
  - `mole-rpc` and `json-rpc-dual-engine` are hardly used.
  - Plain Node.js without a library is what the test server already shows.

### 2. TypeScript that Node.js runs directly

- Node.js removes the types of a `.ts` file when it loads it, by default from 22.18 and 23.6 on. There is no build step and no output folder.
- **`tsconfig.json`:**
  - `erasableSyntaxOnly` refuses what Node.js cannot remove, such as `enum`.
  - `verbatimModuleSyntax` makes type imports explicit.
  - `module` `nodenext`, `noEmit` and `strict`.
- **`package.json`:**
  - `"type": "module"` and `engines` `>=24`: Node.js 24, a line with long-term support. Daniel chose it on 2026-11-10 over Node.js 26, the newest line with long-term support.
  - The versions are exact, with `package-lock.json` committed, so that `npm ci` installs the same everywhere.
  - `@types/node` is that of Node.js 24, the oldest version that the example supports, so that `tsc` refuses an API that only newer versions have.
  - The scripts `start` (`node src/server.ts`) and `check` (`tsc`).
- **Alternatives:**
  - JavaScript would show no types of the protocol.
  - TypeScript with a build step adds a step before every start.
  - Daniel chose this one.

### 3. Files

- **`src/protocol.ts`:** the types of the messages that the example sends and receives, after the data structures of the protocol page, with the field names of the wire.
- **`src/server.ts`:** the command line, the transports and the handlers.
- **`README.md`:** how to install it with `npm ci`, how to start it in each transport, and the keywords.

The protocol page shows `src/server.ts` in full, as it does with the code of the Python example.

### 4. The library and its keywords

- **`NodeLibrary`** has three keywords, each showing one thing:
  - `Echo` returns its `message`. Before that, it sends the log message `Echoing <message>` with `robot/log`.
  - `Sum Of` declares its argument `numbers` as `list[int]` and its return type as `int`, and returns the sum.
  - `Fail With` fails with its `message`. It answers with a `RunKeywordResult` whose `error` holds the message and the type `Error`, as the reference server does for a failed keyword.
- **Handshake:** the server keeps the state of the handshake for each connection. An import or a keyword call before `robot/initialized` gets `-32000`.
- **An unknown keyword** gets `-32001` with the message of the Python example.
- **Imports:** every import gets a token of its own, and the server answers an import of any name with its library, as the Python example does.
- **The rest of the session:**
  - `robot/initialize` states `support_exit` and no `pickle_protocol`.
  - The server sends all its log messages, so `robot/set_log_level` changes nothing.
  - `robot/finalize_library` and `robot/shutdown` answer with an empty object.
  - `robot/exit` closes the connection.

### 5. Command line and transports

- **Parsing:** `parseArgs()` of `node:util` reads `--port PORT`, `--stdio` and `--pipe ADDRESS`, which also takes `--pipe=ADDRESS`. It refuses unknown options.
- **The transports:**
  - Without `--stdio` and `--pipe`, the server listens on `127.0.0.1` at the port, by default `8271`, and serves every connection on its own. With `--port 0`, the system chooses the port.
  - With `--stdio`, it serves one client over stdin and stdout.
  - With `--pipe`, it connects to the address and serves that one client.
  - With `--stdio` or `--pipe`, the process ends when the connection ends.
- **Output:** the server writes what it reports to stderr, with `console.error()`, in every transport. Over stdio, stdout belongs to the messages, and one rule for all transports keeps that simple. At the start in TCP mode, the line `listening on 127.0.0.1:<port>` gives the port.

### 6. Workspace, Git and CI

- **`pyproject.toml`:** `exclude = ["examples/node-robot-jsonrpcserver"]` in `[tool.uv.workspace]`.
- **`.gitignore`:** `examples/node-robot-jsonrpcserver/node_modules/`.
- **`.github/workflows/ci.yml`:**
  - **The test jobs,** also that of the minimum of Robot Framework, install Node.js 24 with `actions/setup-node` before the tests, and run `npm ci` in the example folder. The Node suites of the test server then run on the same Node.js.
  - **The lint job** installs Node.js 24, runs `npm ci` and checks the types with `npm run check`.

### 7. Tests

- **Unit tests in `tests/examples/test_node_example_server.py`:**
  - They start the example as a process: over TCP with `--port 0`, reading the port from its line on stderr; with `create_stdio_subprocess()` and `--stdio`; and with `create_pipe_subprocess()`.
  - They talk to it with a `JsonRpcPeer` and the types of the protocol package, as `tests/examples/test_example_server.py` does, and cover every scenario of the requirement.
  - They skip without `node` or without the installed packages, except in CI, with the hint to run `npm ci` in the example folder.
  - The path of the example and this rule are in `tests/node_example.py`, which the test of the docs example uses too.
- **Robot suites `atests/stdio/node_example.robot` and `atests/pipe/node_example.robot`:**
  - `Echo` with its log message, from `LogCapture`, `Sum Of` with a list, `Fail With` with `Run Keyword And Expect Error`, and a keyword after the failure.
  - The commands come from `atests/resources/stdio_vars.py` and `pipe_vars.py`, with the path of the example from `atests/resources/paths.py`.
  - They skip as the unit tests do.
- **Docs example `docs/examples/node-server/`:**
  - `echo.robot` over TCP, against the server started in the example folder with `node src/server.ts`.
  - `echo_pipe.robot` with the command as a list: `pipe:`, `node` and the path from `${CURDIR}`.
  - `tests/docs/test_docs_examples.py` runs both, with the commands of the page.
- **Windows:** the test VM runs the tests and suites, also over a named pipe.

### 8. Documentation

- **`docs/src/content/docs/reference/protocol.mdx`:** a section "Example: a server in Node.js" after the Python example. It contains:
  - why `vscode-jsonrpc` fits;
  - how to install and start the server;
  - the code of `src/server.ts`;
  - the transports;
  - that the server gets plain and typed JSON and no pickles;
  - the two suites of the docs example.
- **`docs/src/content/docs/roadmap.mdx`:** the example in Node.js is available; Rust, Java and .NET stay planned.
- **`AGENTS.md`:** the orientation names the new folder.
- **`CONTRIBUTING.md`:** `npm ci` in the folder, for the tests of the example.

## Risks / Trade-offs

- [Node.js older than 22.18 does not run the `.ts` files, and Node.js older than 24 is not tested] → `engines` states 24, the README names it, and CI uses Node.js 24.
- [Some versions of Node.js write a warning about type stripping to stderr] → stderr is for reports, and the messages are untouched.
- [`npm ci` needs the network in CI and for local tests] → The tests skip without the installed packages, except in CI. The test server keeps covering the client without them.
- [Two servers in Node.js] → They have different jobs: the test server shows the wire without a library, the example shows how to write a server.
