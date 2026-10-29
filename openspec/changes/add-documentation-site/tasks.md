# Tasks

## 1. Site

- [ ] 1.1 Create the Starlight project in `docs/` from the Starlight template with npm, with `site: 'https://imbus.github.io'`, `base: '/robotframework-jsonrpcremote'`, the title `JsonRpcRemote`, a link to the GitHub repository, the sidebar groups Getting started, Guides and Reference, and `starlight-links-validator` (design decision 1). Add `docs/node_modules/`, `docs/.astro/` and `docs/examples/container/wheels/` to `.gitignore`. Verify that `npm ci` and `npm run build` in `docs/` succeed, and that `uv run ruff check .` and `uv run ruff format --check .` still pass

## 2. Pages and examples

Each example lives in `docs/examples/<name>/` with the files its page shows and a `run.sh` with the commands the page names (design decision 2); its suite is the Robot test that verifies the page. Verify each task by running `uv run bash docs/examples/<name>/run.sh` from the repository root and by `npm run build` in `docs/`, which also checks the links.

- [ ] 2.1 `getting-started`: a small library, a suite and a `run.sh` that starts `robot-jsonrpcremote-server` on the loopback address in the background, runs the suite and stops the server; the page Getting started, with installation and the example files
- [ ] 2.2 `stdio`: the getting-started suite over a `stdio:` URI, where the client starts the server; the guide on TCP and stdio, including that stdio is POSIX-only and serves one client
- [ ] 2.3 `rpc-scope`: a suite that shows a session per test with `rpc_scope=TEST` against a library that keeps a value; the guide on sessions and `rpc_scope`
- [ ] 2.4 `connect-retry`: a suite with `rpc_connect_retry_timeout` and `rpc_connect_retry_interval` whose server `run.sh` starts only after the import began; the guide on lost connections and connect retry, including the warning after a reconnect
- [ ] 2.5 `several-libraries`: one server with two libraries and a suite that imports both; the guide on hosting several libraries, including that the server runs keywords one after another, so a blocking keyword blocks all clients
- [ ] 2.6 `container`: a `Dockerfile` that installs `${PACKAGES}` inside `RUN --mount=type=bind,target=/context`, defaulting to `robotframework-jsonrpcremote-server` from PyPI, and starts the server with `--bind 0.0.0.0`; a `run.sh` that builds the image with `--build-arg PACKAGES="${PACKAGES:-robotframework-jsonrpcremote-server}"`, runs it with the port published on `127.0.0.1` only, runs the getting-started suite against it and removes the container (design decision 3); the guide on the server in a container and as a Kubernetes sidecar, the latter in text. Verify additionally with wheels built from the repository: `uv build --package jsonrpcpeer --package robotframework-jsonrpcremote-protocol --package robotframework-jsonrpcremote-server -o docs/examples/container/wheels`, then `PACKAGES="/context/wheels/*.whl" uv run bash docs/examples/container/run.sh`
- [ ] 2.7 `own-server`: a `run.sh` that starts `simple-robot-jsonrpcserver` and runs a suite against it; the protocol page in Reference, with the specification moved from `packages/protocol/README.md` and the example server's source included with `?raw`; verify that the page names every message of `robot_jsonrpcremote_protocol`
- [ ] 2.8 The reference pages for the arguments of `JsonRpcRemote` and for the server's options and environment variables. Verify that every argument of `JsonRpcRemote.__init__` and every option in `uv run --all-packages robot-jsonrpcremote-server --help` appears with its default

## 3. Publishing

- [ ] 3.1 Add `.github/workflows/docs.yml` with the jobs `build` (`withastro/action@v6`, `path: docs`), `examples` (Linux, uv synced as in `ci.yml`, the container wheels built as in 2.6, then every `docs/examples/*/run.sh` with `uv run`, `timeout-minutes: 20`) and `deploy` (needs both, only for pushes to `main`, `pages: write` and `id-token: write`, environment `github-pages`, `actions/deploy-pages@v5`) (design decision 4). Verify by loading the workflow with `yaml.safe_load`: three jobs, the condition and the permissions of `deploy`, and that `examples` runs every example directory

## 4. READMEs, rule and server

- [ ] 4.1 Shorten the READMEs as design decision 5 says. Verify that `git grep -n -i -E 'multiplex|progress update|language agnostic|bind 0\.0\.0\.0|Directory for Robot output' -- '*.md' ':!openspec' ':!docs'` finds nothing, that each README links to the site, and that `packages/protocol/README.md` keeps a summary of the protocol
- [ ] 4.2 Add the documentation rule as the fifth rule under `rules.tasks` in `openspec/config.yaml`, as a bullet in `AGENTS.md` and as a paragraph in `CONTRIBUTING.md` (design decision 6). Verify that `openspec instructions tasks --change fix-keyword-failure-reporting --json` returns five rules and that the three texts state the same rule
- [ ] 4.3 Remove the `ResultWriter` branch and its import from `RobotRemoteContext.run()` and say in the help text of `--outputdir` that it sets `${OUTPUT_DIR}` and that the server writes no output files (design decision 7). Verify that `git grep -n ResultWriter -- packages` finds nothing and that `uv run --all-packages robot-jsonrpcremote-server --help` shows the new text; the unit tests and Robot suites of 5.1 and 5.2 cover the server, since the removed branch could never run and nothing that a test could observe changes

## 5. Integration checks

- [ ] 5.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [ ] 5.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass
- [ ] 5.3 Run `npm ci` and `npm run build` in `docs/` and every `docs/examples/*/run.sh` once more, the container example with the wheels from 2.6; verify all pass. The examples describe behavior that exists already, so there is no part of this change they could fail without; a broken page or example fails here
- [ ] 5.4 Commit the site, the examples, the workflow, the READMEs, the rule, the server change, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`): subject `docs: add a documentation site with runnable examples`, a body that explains why the site exists, how the examples stay true, the corrections to the READMEs, the documentation rule and the removed dead branch, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Daniel pushes `main`; check that the docs workflow passes `build`, `examples` and `deploy`, and that https://imbus.github.io/robotframework-jsonrpcremote/ shows the site. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`; it has no delta specs.
- Commit the archive as its own signed commit: `docs(openspec): archive add-documentation-site`, then run `uv run ruff format --check .`.
- Set DOC-3, DOC-1, DOC-2 and SERVER-4 to done and SERVER-5 to documented in `playground/anforderungen-und-ideen.md`.
