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

- **Getting started:** install, start a server, run a first suite; the page Why JsonRpcRemote, with the comparison with the Remote library, and the status and roadmap (decision 8).
- **Guides:** TCP and stdio; sessions and `rpc_scope`; lost connections and connect retry; the server in a container and as a sidecar; several libraries on one server.
- **Reference:** the arguments of `JsonRpcRemote`; the server's options and environment variables; the protocol, moved from `packages/protocol/README.md`, with the hand-written example server as a sample implementation. The page describes the values as they travel today; the README's draft conventions for values of other languages are on the roadmap page (decision 8); the draft for resolving type names is not moved, since it is still undecided.

`.gitignore` gets `docs/node_modules/` and `docs/.astro/` in place of the template's own `docs/.gitignore`; `dist/` is already there.

A route middleware in `docs/src/routeData.ts` puts a banner on every page: the project is pre-alpha and under active development, the site describes `main`, which may differ from the latest release, and features are still being added; it links to the status and roadmap. Starlight sets banners per page only, and the middleware is one file to change or delete when the status changes.

- **Alternative:** a Python tool such as MkDocs, inside the uv workspace. Daniel asked for Starlight; its `<Code>` component with `?raw` is what keeps the examples and the page identical.

### 2. Examples are directories with the files the page shows and a `run.sh`

Each example lives in `docs/examples/<name>/` with the files its page includes and a `run.sh` with the commands the page names, which CI runs. The pages show the files and the commands, not the `run.sh`: readers work in an IDE, and the script would only repeat the page (Daniel, 2026-10-30). The `run.sh` files wait until the server accepts connections, and the container's until the server in the container has logged that it is up, so the suites stay as a reader writes them; only the connect-retry example sets `rpc_connect_retry_timeout` (Daniel, 2026-10-30, after the review: the reader starts the server first, and the latest release, 0.2.0, does not know the option). The examples:

- `getting-started`: a small library, a server started on the loopback address, a suite;
- `stdio`: the same suite over `stdio:`, where the client starts the server itself;
- `rpc-scope` and `connect-retry`: a suite each, against a server started in `run.sh`;
- `several-libraries`: one server with two libraries;
- `container`: a `Dockerfile`, see decision 3;
- `own-server`: runs `examples/simple-robot-jsonrpcserver` with its suite, for the protocol page.

### 3. The container example installs the current code in CI through a build argument

The `Dockerfile` installs `${PACKAGES}` with pip, a build argument that defaults to `robotframework-jsonrpcremote-server` from PyPI. It installs inside `RUN --mount=type=bind,target=/context`, which mounts the build context without copying it into the image. The example's `run.sh` first builds the wheels of `jsonrpcpeer`, the protocol and the server into the example's `wheels/`, which `.gitignore` lists, and passes `--build-arg PACKAGES="/context/wheels/*.whl"`, so the example tests the current code wherever it runs (changed on 2026-10-30, after the review). The server in the container binds to `0.0.0.0`, which is needed there and is the only place the site uses it, with a note why; `docker run` publishes the port on `127.0.0.1` only.

- **Alternative:** install from PyPI in CI. The image would then test the released version, not the code of the change.
- **Alternative:** copy the repository into the image. The reader's `Dockerfile` would need the repository, too.

### 4. One workflow builds, checks and publishes the site and runs the examples

`.github/workflows/docs.yml` runs on pushes to `main`, on pull requests and on demand:

- `build` uses `withastro/action@v6` with `path: docs`; `starlight-links-validator` fails the build on broken internal links.
- `examples` runs on Linux: it installs uv and syncs the workspace, as `ci.yml` does, and runs each `docs/examples/*/run.sh` with `uv run --all-packages`; Docker is available on the runner.
- `deploy` needs both and runs only for pushes to `main`, with `pages: write` and `id-token: write`, in the `github-pages` environment, with `actions/deploy-pages@v5`.

- **Alternative:** add the jobs to `ci.yml`. The site's jobs would mix with the Python matrix and its permissions; a workflow of its own keeps the deploy permissions in one place.

### 5. READMEs point to the site and keep what PyPI shows

- `README.md`: what the library is for and its features as they are meant to be (decision 8), the pre-alpha status, requirements, installation, the getting-started suite in short, links to the site. Multiplexing and progress updates are listed as planned, on the site's roadmap, not as features.
- `packages/server/README.md`: installation, the quick start on the loopback address, a link to the reference.
- `packages/protocol/README.md`: a summary and a link to the protocol page.
- `packages/jsonrpcpeer/README.md` and `examples/simple-robot-jsonrpcserver/README.md`: a link to the site.

### 6. The documentation rule stands where the testing rule stands

A fifth rule under `rules.tasks` in `openspec/config.yaml`, a bullet in `AGENTS.md` and a paragraph in `CONTRIBUTING.md`: a change with user-visible behavior updates the site and its examples in the same change, and its review checks the implementation against them. The overview pages, the home page, the page Why JsonRpcRemote and the README, describe JsonRpcRemote as it is meant to be; guides and references describe what works today, without listing gaps or giving workarounds; the roadmap page says what is available and what is planned, and every change that implements a feature updates the documentation, the roadmap included (added on 2026-10-30).

### 7. The server keeps passing `None` and loses the dead branch

`RobotRemoteContext.run()` loses the `ResultWriter` branch and its import; the `None` values stay, because they are what keeps Robot Framework from writing files. The help text of `--outputdir` says that it sets `${OUTPUT_DIR}` for the libraries and that the server writes no output files.

### 8. The site says what JsonRpcRemote is for, what works today and what is planned

Added on 2026-10-30 after Daniel's review of the pages:

- JsonRpcRemote is a modern alternative to Robot Framework's Remote library, built on JSON-RPC 2.0, a simple standard with implementations in every common programming language. The home page, Getting started and the README say this first, the overview pages with the features as they are meant to be: the persistent, bidirectional connection with live logs, stdio, several libraries on one server, almost any Robot Framework library remote without code, library arguments from the suite, sessions, and lost connections with connect retry.
- The page Why JsonRpcRemote says why keywords run on a remote server and what JsonRpcRemote does better than the Remote library, and compares its design with the Remote library and its Python server in a table, without the gaps of the current implementation (Daniel, 2026-10-30). Its statements about the Remote library come from the source of Robot Framework and `robotremoteserver` and from the User Guide.
- The project is pre-alpha. A page "Status and roadmap" lists what is available and what is planned; the banner on every page says so and links there. It has no list of limitations: nearly all of them are planned features, and pickles and one keyword at a time are properties of the Python implementation and of Robot Framework, not limitations of JsonRpcRemote (Daniel, 2026-10-30). That remote keywords run in the server's Robot Framework execution is described in the server reference. Overview pages describe the state we aim for; guides and references describe what works today, without listing gaps or giving workarounds (Daniel, 2026-10-30). Planned features, including the conventions for values of other languages, are listed on the roadmap page only. The roadmap is a public summary, not the internal backlog.
- The protocol is language-agnostic by design. The protocol page says so and describes the values as they travel today: JSON values, and Python pickles between Python peers.

## Risks / Trade-offs

- **[Node.js in a Python project]** → The toolchain stays in `docs/`; Python contributors only need it to preview the site, and CI builds it.
- **[Examples slow down the docs workflow]** A server start per example and one image build. → They run in one Linux job, apart from the Python matrix.
- **[The `Dockerfile` shows a build argument the reader does not need]** → A comment says it is for CI and that the default installs from PyPI.
- **[Links with `base`]** Internal links in Markdown must start with `/robotframework-jsonrpcremote/`. → `starlight-links-validator` reports links that do not resolve.
- **[The site and the code drift apart again]** → The examples run in CI, and the documentation rule makes later changes update the site.
