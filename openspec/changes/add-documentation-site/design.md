# Design

## Context

See proposal.md for the motivation and the decisions confirmed on 2026-10-29.

**Today:**

- The user documentation is the READMEs: `README.md` (overview, installation, usage, protocol notes), `packages/server/README.md`, `packages/protocol/README.md` with the protocol specification, `packages/jsonrpcpeer/README.md` and `examples/simple-robot-jsonrpcserver/README.md`, a hand-written server built on `jsonrpcpeer`.
- CI is `.github/workflows/ci.yml` with lint, the Python matrix and the Robot Framework minimum. GitHub Pages is enabled with GitHub Actions as its source; nothing is deployed yet.
- The server passes `output`, `log` and `report` as `None` to Robot Framework, so it writes no output files, and the `ResultWriter` branch at the end of `RobotRemoteContext.run()` can never run. `--outputdir` only sets `${OUTPUT_DIR}`.

**Tools** (checked on 2026-10-29 in the Starlight and Astro docs):

- In an MDX page, `import code from '…?raw'` loads a file as a string, and `<Code code={code} lang="…" title="…" />` from `@astrojs/starlight/components` shows it.
- `withastro/action@v6` installs, builds and uploads a site in a subdirectory (`path`), with Node 24 by default; `actions/deploy-pages@v5` publishes it. Pages for a project repository needs `site: 'https://imbus.github.io'` and `base: '/robotframework-jsonrpcremote'` in `astro.config.mjs`.
- The community plugin `starlight-links-validator` fails the build on broken internal links; Starlight's own docs use it.

## Goals / Non-Goals

**Goals:**

- One place that explains how to use the library and the server, where every example is a file that CI runs against the current code.
- Every later change of the series documents its user-visible behavior there.

**Non-Goals:**

- Versioned docs, search beyond Starlight's built-in one, a custom domain, translations.
- A Kubernetes manifest: the sidecar pattern is described in text, since CI cannot run a manifest without a cluster.

## Decisions

### 1. A plain Starlight project in `docs/`

`docs/` holds a Starlight project created from the Starlight template with npm, committed with `package-lock.json`, so that `withastro/action` finds the package manager. The pages are MDX under `docs/src/content/docs/`, in three sidebar groups:

- **Getting started:** install, start a server, run a first suite.
- **Guides:** TCP and stdio; sessions and `rpc_scope`; lost connections and connect retry; the server in a container and as a sidecar; several libraries on one server.
- **Reference:** the arguments of `JsonRpcRemote`; the server's options and environment variables; the protocol, moved from `packages/protocol/README.md`, with the hand-written example server as a sample implementation.

`.gitignore` gets `docs/node_modules/` and `docs/.astro/`; `dist/` is already there.

- **Alternative:** a Python tool such as MkDocs, inside the uv workspace. Daniel asked for Starlight; its `<Code>` component with `?raw` is what keeps the examples and the page identical.

### 2. Examples are directories with the files the page shows and a `run.sh`

Each example lives in `docs/examples/<name>/` with the files its page includes and a `run.sh` that holds the commands the page tells the reader to run, so the page can include `run.sh`, too. Suites against a TCP server use `rpc_connect_retry_timeout`, which avoids a race with the server start in CI and is what a sidecar setup needs anyway. The examples:

- `getting-started`: a small library, a server started on the loopback address, a suite;
- `stdio`: the same suite over `stdio:`, where the client starts the server itself;
- `rpc-scope` and `connect-retry`: a suite each, against a server started in `run.sh`;
- `several-libraries`: one server with two libraries;
- `container`: a `Dockerfile`, see decision 3;
- `own-server`: runs `examples/simple-robot-jsonrpcserver` with its suite, for the protocol page.

### 3. The container example installs the current code in CI through a build argument

The `Dockerfile` installs `${PACKAGES}` with pip, a build argument that defaults to `robotframework-jsonrpcremote-server` from PyPI. It installs inside `RUN --mount=type=bind,target=/context`, which mounts the build context without copying it into the image. CI first builds the wheels of `jsonrpcpeer`, the protocol and the server into the example's `wheels/`, which `.gitignore` lists, and passes `--build-arg PACKAGES="/context/wheels/*.whl"`. The server in the container binds to `0.0.0.0`, which is needed there and is the only place the site uses it, with a note why; `docker run` publishes the port on `127.0.0.1` only.

- **Alternative:** install from PyPI in CI. The image would then test the released version, not the code of the change.
- **Alternative:** copy the repository into the image. The reader's `Dockerfile` would need the repository, too.

### 4. One workflow builds, checks and publishes the site and runs the examples

`.github/workflows/docs.yml` runs on pushes to `main`, on pull requests and on demand:

- `build` uses `withastro/action@v6` with `path: docs`; `starlight-links-validator` fails the build on broken internal links.
- `examples` runs on Linux: it installs uv and syncs the workspace, as `ci.yml` does, and runs each `docs/examples/*/run.sh` with `uv run`; Docker is available on the runner.
- `deploy` needs both and runs only for pushes to `main`, with `pages: write` and `id-token: write`, in the `github-pages` environment, with `actions/deploy-pages@v5`.

- **Alternative:** add the jobs to `ci.yml`. The site's jobs would mix with the Python matrix and its permissions; a workflow of its own keeps the deploy permissions in one place.

### 5. READMEs point to the site and keep what PyPI shows

- `README.md`: what the library does, requirements, installation, the getting-started suite in short, a link to the site. Multiplexing, progress updates and the claim that the protocol is language-agnostic go; the site's protocol page says what holds today.
- `packages/server/README.md`: installation, the quick start on the loopback address, a link to the reference.
- `packages/protocol/README.md`: a summary and a link to the protocol page.
- `packages/jsonrpcpeer/README.md` and `examples/simple-robot-jsonrpcserver/README.md`: a link to the site.

### 6. The documentation rule stands where the testing rule stands

A fifth rule under `rules.tasks` in `openspec/config.yaml`, a bullet in `AGENTS.md` and a paragraph in `CONTRIBUTING.md`: a change with user-visible behavior updates the site and its examples in the same change, and its review checks the implementation against them.

### 7. The server keeps passing `None` and loses the dead branch

`RobotRemoteContext.run()` loses the `ResultWriter` branch and its import; the `None` values stay, because they are what keeps Robot Framework from writing files. The help text of `--outputdir` says that it sets `${OUTPUT_DIR}` for the libraries and that the server writes no output files.

## Risks / Trade-offs

- **[Node.js in a Python project]** → The toolchain stays in `docs/`; Python contributors only need it to preview the site, and CI builds it.
- **[Examples slow down the docs workflow]** A server start per example and one image build. → They run in one Linux job, apart from the Python matrix.
- **[The `Dockerfile` shows a build argument the reader does not need]** → A comment says it is for CI and that the default installs from PyPI.
- **[Links with `base`]** Internal links in Markdown must start with `/robotframework-jsonrpcremote/`. → `starlight-links-validator` reports links that do not resolve.
- **[The site and the code drift apart again]** → The examples run in CI, and the documentation rule makes later changes update the site.
