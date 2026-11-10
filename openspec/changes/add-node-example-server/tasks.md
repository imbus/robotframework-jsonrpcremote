# Tasks

Every new test is run once against the code without the part of the change it covers, and must fail there.

- **Time limits:** a server that never answers can hang a test, so these checks and all runs on the Windows test VM have a hard time limit.
- **The VM:** Daniel starts it. When a task needs it, ask him and wait.
- **Copies to the VM:** no `__pycache__` and no `node_modules`; the VM runs `npm ci` itself.

## 1. The example

- [ ] 1.1 Create `examples/node-robot-jsonrpcserver/` (design decisions 1 to 5):
  - **`package.json`:** `private`, `"type": "module"`, `engines` `>=22.18`, the exact versions of `vscode-jsonrpc`, `typescript` and `@types/node`, and the scripts `start` and `check`.
  - **`package-lock.json`:** from `npm install`.
  - **`tsconfig.json`**, **`src/protocol.ts`** and **`src/server.ts`**.
  - **Configuration:** add `exclude` to `[tool.uv.workspace]` in `pyproject.toml`, and the `node_modules` of the example to `.gitignore`.

  Verify:
  - `npm ci` and `npm run check` pass in the folder.
  - `uv sync --all-packages` and `uv lock --check` pass.
  - `node src/server.ts --port 0` writes `listening on 127.0.0.1:<port>` to stderr.
  - `node src/server.ts --unknown` fails with the error of `parseArgs()`.

  Counter-check: without `exclude`, `uv lock --check` must fail.
- [ ] 1.2 Add `tests/examples/test_node_example_server.py` (design decision 7). It covers every scenario of the requirement A server in Node.js can serve the protocol with a JSON-RPC library:
  - A whole session over TCP, over stdio and over a pipe, each from `robot/initialize` to `robot/exit`, with the end of the process for stdio and the pipe.
  - The log message of `Echo` arrives before its result.
  - `Sum Of` with `[1, 2, 39]` returns `42`.
  - `Fail With` answers with a `RunKeywordResult` whose `error` holds the message, and the next call works.
  - The answer to `robot/initialize` holds no `pickle_protocol`.
  - An import and a keyword call before `robot/initialized` get `-32000`.
  - An unknown keyword gets `-32001` and the message `Keyword 'Gone' not found in library 'NodeLibrary'.`

  The tests skip without `node` or without the installed packages, except in CI, where they fail.

  Counter-checks:
  - Without the check of the handshake, the tests for `-32000` must fail.
  - Without the log message of `Echo`, its test must fail.
  - With `pickle_protocol` in the capabilities, No pickles must fail.
  - Without the handling of `--pipe`, the session over a pipe must fail.
- [ ] 1.3 Write `examples/node-robot-jsonrpcserver/README.md`: what the example shows, Node.js 22.18 or later, `npm ci`, the start in each transport, the keywords and the type check. Verify that the commands of the README run as written, on Linux and on the VM.

## 2. Robot suites

- [ ] 2.1 Add `atests/stdio/node_example.robot` and `atests/pipe/node_example.robot` (design decision 7):
  - **Tests:** `Echo` with its log message from `LogCapture`, `Sum Of` with a list, `Fail With` with `Run Keyword And Expect Error`, and a keyword call after the failure.
  - **Commands:** in `atests/resources/stdio_vars.py` and `pipe_vars.py`, with the path of the example from `atests/resources/paths.py`.
  - **Skipping:** as the unit tests.

  Verify locally and on the VM.

  Counter-checks:
  - Against the example without the handling of `--stdio`, the stdio suite must fail.
  - Without the handling of `--pipe`, the pipe suite must fail.

## 3. CI

- [ ] 3.1 In `.github/workflows/ci.yml` (design decision 6):
  - **The test jobs,** also that of the minimum of Robot Framework, install Node.js 24 with `actions/setup-node`, in its current major version, and run `npm ci` in the example folder before the tests.
  - **The lint job** installs Node.js 24, runs `npm ci` and `npm run check` in the example folder.

  Verify that the file parses as YAML and that each new step runs locally as written. CI itself runs in the workflow follow-up.

## 4. Documentation

- [ ] 4.1 Document the example (design decision 8):
  - **`docs/src/content/docs/reference/protocol.mdx`:** the section "Example: a server in Node.js", with the code of `src/server.ts` and the two suites of the docs example.
  - **`docs/examples/node-server/`:** `echo.robot` over TCP and `echo_pipe.robot` with the command as a list.
  - **`tests/docs/test_docs_examples.py`:** `test_node_server` starts the example in its folder with `node src/server.ts`, runs `echo.robot` and then `echo_pipe.robot`. It skips as the unit tests do.
  - **`docs/src/content/docs/roadmap.mdx`:** the example in Node.js is available; Rust, Java and .NET stay planned.
  - **`AGENTS.md`** names the folder in the orientation, and **`CONTRIBUTING.md`** says to run `npm ci` in it for the tests of the example.

  Review the implementation of groups 1 and 2 against the pages. Verify with `uv run --all-packages pytest tests/docs/test_docs_examples.py` on Linux and on the VM, and with `npm ci` and `npm run build` in `docs/`, which also checks the links. Counter-check: against the example on another port than 8271 by default, `test_node_server` must fail.

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform win32` and `uv run --all-packages pytest`, and `npm run check` in the example folder; verify all pass.
- [ ] 5.2 Run `uv run --all-packages robotcode run`, and with `--with "robotframework==7.2"`; verify all Robot suites pass, the new suites included.
- [ ] 5.3 On the Windows test VM:
  - Check that its Node.js is 22.18 or later. If it is older, ask Daniel before installing another one.
  - Run `npm ci` in the example folder.
  - Run the unit tests and `robotcode run` with `uv sync --all-packages` and hard time limits, on Python 3.12 and 3.15.

  Verify that all pass, that the new tests and suites ran and were not skipped, and that no process stays behind.
- [ ] 5.4 Commit the change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`). Stage only the paths of this change, because another session may work on `main`, check the staged files, and commit in a separate step.
  - **Subject:** `feat(examples): add an example server in Node.js`.
  - **Body:** why an example in another language, why `vscode-jsonrpc` and TypeScript that Node.js runs directly, the transports, and that the test server stays.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`. Check that CI and the docs workflow pass. The uploaded `output.xml` must show the new suites on `ubuntu-latest`, `macos-latest` and `windows-latest`, not skipped. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive` and sync its delta spec into `openspec/specs/protocol`.
- In the backlog, note the example in Node.js under DOC-5, with Rust as the next part.
