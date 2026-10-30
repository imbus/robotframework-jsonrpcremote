# Proposal

## Why

The library has no user documentation beyond its READMEs. The root README mixes overview, installation, usage and protocol notes, and the READMEs of the server, protocol and peer packages each describe their own part. Someone who wants to run tests against a remote library, for example with the server as a sidecar container as in issue #2, has to piece together how to start the server, import the library, choose a transport, and set `rpc_scope` and connect retry.

The READMEs have also drifted from the code, and nothing checks them:

- they advertise connection multiplexing, although the client opens one connection per library instance, and progress updates, which do not exist;
- they describe `--outputdir` as the directory for Robot output files, but the server writes none and only sets `${OUTPUT_DIR}`;
- they do not say that the server runs keywords one after another, so one blocking keyword blocks all clients;
- they call the protocol language-agnostic without saying that values other than JSON scalars travel as Python pickles today, which only a Python peer can read;
- the server README's quick start binds the server to all network interfaces instead of the loopback address;
- the declared Robot Framework minimum had drifted to 7.4 until `fix-robot-framework-compatibility` raised it to 7.2.

A small documentation site with guides and runnable examples addresses both. If every example on it is a file that CI runs, the site cannot promise what the code does not do, and every later change can describe its user-visible behavior there and be reviewed against it.

Found in the project review of 2026-10-27 (items DOC-3, DOC-1, DOC-2, SERVER-4 and SERVER-5).

## What Changes

- **Site:** a small Starlight site (Astro) in `docs/`:
  - getting started: install the library and the server, start a server, run a first suite;
  - guides: TCP and stdio, sessions and `rpc_scope`, lost connections and connect retry, the server as a container or Kubernetes sidecar, hosting several libraries;
  - reference: the arguments of `JsonRpcRemote`, the server's options and environment variables, and the protocol for implementing a server in another language;
  - what JsonRpcRemote is for: a comparison with Robot Framework's Remote library, and the status and roadmap of the pre-alpha project.

  Its guides and references describe the behavior as it is, including the corrections above; its overview pages describe JsonRpcRemote as it is meant to be.
- **Runnable examples:** every example on the site is a file in the repository that the page includes with Starlight's `<Code>` component and a `?raw` import. A CI job runs all examples against a real server.
- **READMEs:** the root README becomes a short overview: what the library is for, its features, its pre-alpha status, installation, a minimal example and links to the site. The package READMEs keep what their PyPI pages need and link to the site. All examples use the default loopback address.
- **Build and publishing:** CI builds the site and checks its links, and a workflow publishes it from `main`.
- **Workflow rule:** `openspec/config.yaml` gets a task rule next to the four on tests, and `AGENTS.md` and `CONTRIBUTING.md` state it as they state those: a change with user-visible behavior updates the site and its runnable examples, and its review checks the implementation against them. The overview pages describe JsonRpcRemote as it is meant to be, guides and references what works today, without gaps or workarounds, and the roadmap page what is available and what is planned; every change that implements a feature updates the documentation.
- **Server output files:** the unreachable `ResultWriter` branch in the server's runner is removed, and the help text of `--outputdir` says that it only sets `${OUTPUT_DIR}`.
- No product behavior changes, so the change has no spec delta (`skip_specs: true`).

Decisions confirmed on 2026-10-29:

- The site lives in `docs/` of this repository. Its Node.js toolchain stays separate from the Python workspace.
- It is published on GitHub Pages of `imbus/robotframework-jsonrpcremote`, enabled on 2026-10-29 with GitHub Actions as its source.
- The protocol specification moves from `packages/protocol/README.md` to the site; the README keeps a summary for its PyPI page and a link.
- The server gets no options for Robot output files; describing `--outputdir` correctly is enough.
- The examples run in a CI job of their own on Linux, which starts the server as the site shows.
- The container guide has a `Dockerfile` example that CI builds from the current code; the Kubernetes sidecar is described in text only.

Decided while implementing, on 2026-10-29 and 2026-10-30:

- The site describes `main`, while the latest release on PyPI, 0.2.0, lacks connect retry, the stdio transport and the detection of lost connections. A banner on every page says that the project is pre-alpha and under active development, that the site describes `main`, which may differ from the latest release, and that features are still being added; the installation stays `pip install` from PyPI.
- JsonRpcRemote is positioned as a modern alternative to Robot Framework's Remote library, built on JSON-RPC 2.0, a simple standard that every common programming language supports. Besides a page on why JsonRpcRemote exists and what it does better than the Remote library, the site gets a page on what is available and what is planned.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **New:** `docs/` with the Astro project, its pages and the example files; a workflow that publishes the site.
- **CI:** jobs that build the site, check its links and run the examples, next to the matrix from `add-ci-version-matrix`. The Python tools leave the site alone: ruff follows `.gitignore`, which gets the site's `node_modules` and `.astro`, and pytest, mypy and robotcode only look at their configured paths.
- **Docs:** `README.md`, `packages/server/README.md`, `packages/protocol/README.md`, `packages/jsonrpcpeer/README.md`, `examples/simple-robot-jsonrpcserver/README.md`, and for the workflow rule `AGENTS.md` and `CONTRIBUTING.md`.
- **Code:** `packages/server/src/robot_jsonrpcremote_server/_runner.py` (the unreachable `ResultWriter` branch) and the help text of `--outputdir` in `__main__.py`.
- **Workflow:** `openspec/config.yaml`.
- **Package metadata:** the `Documentation` URL in the four `pyproject.toml` points to the site.
- **Order:** after `add-ci-version-matrix`, which is done; before `fix-keyword-failure-reporting` and every later change, which document their user-visible behavior on the site.
