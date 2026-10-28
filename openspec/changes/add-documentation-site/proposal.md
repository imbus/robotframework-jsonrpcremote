# Proposal

## Why

The library has no user documentation beyond its READMEs. The root README mixes overview, installation, usage and protocol notes, and the READMEs of the server, protocol and peer packages each describe their own part. Someone who wants to run tests against a remote library, for example with the server as a sidecar container as in issue #2, has to piece together how to start the server, import the library, choose a transport, and set `rpc_scope` and connect retry.

The READMEs have also drifted from the code, and nothing checks them:

- they advertise connection multiplexing, although the client opens one connection per library instance, and progress updates, which do not exist;
- they describe `--outputdir` as the directory for Robot output files, but the server writes none and only sets `${OUTPUT_DIR}`;
- they do not say that the server runs keywords one after another, so one blocking keyword blocks all clients;
- the declared Robot Framework minimum drifted until `fix-robot-framework-compatibility`.

A small documentation site with guides and runnable examples addresses both. If every example on it is a file that CI runs, the site cannot promise what the code does not do, and every later change can describe its user-visible behavior there and be reviewed against it.

Found in the project review of 2026-10-27 (items DOC-1, DOC-2, SERVER-4 and SERVER-5).

## What Changes

- **Site:** a small Starlight site (Astro) in `docs/`:
  - getting started: install the library and the server, start a server, run a first suite;
  - guides: TCP and stdio, sessions and `rpc_scope`, lost connections and connect retry, the server as a container or Kubernetes sidecar, hosting several libraries;
  - reference: the arguments of `JsonRpcRemote`, the server's options and environment variables, and the protocol for implementing a server in another language.

  It describes the behavior as it is, including the corrections above.
- **Runnable examples:** every example on the site is a file in the repository that the page includes with Starlight's `<Code>` component and a `?raw` import. A CI job runs all examples against a real server.
- **READMEs:** the root README becomes a short overview with installation, a minimal example and a link to the site. The package READMEs keep what their PyPI pages need and link to the site. All examples use the default loopback address.
- **Build and publishing:** CI builds the site and checks its links, and a workflow publishes it from `main`.
- **Workflow rule:** `openspec/config.yaml` gets a rule for tasks: a change with user-visible behavior updates the site and its runnable examples, and its review checks the implementation against them.
- **Server output files:** the unreachable `ResultWriter` branch in the server's runner is removed, and the help text of `--outputdir` says what the option does.
- No product behavior changes, so the change has no spec delta (`skip_specs: true`).

Assumptions recorded for review:

- The site lives in `docs/` of this repository. Its Node.js toolchain stays separate from the Python workspace.
- It is published on GitHub Pages of `imbus/robotframework-jsonrpcremote`; Pages has to be enabled for the repository.
- The protocol specification moves from `packages/protocol/README.md` to the site; the README keeps a summary and a link.
- The server gets no options for Robot output files; describing `--outputdir` correctly is enough.
- The examples run in a CI job of their own on Linux.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **New:** `docs/` with the Astro project, its pages and the example files; a workflow that publishes the site.
- **CI:** jobs that build the site, check its links and run the examples. The ruff check of Markdown files in CI has to handle the site's pages or exclude them.
- **Docs:** `README.md`, `packages/server/README.md`, `packages/protocol/README.md`, `packages/jsonrpcpeer/README.md`, `examples/simple-robot-jsonrpcserver/README.md`.
- **Code:** `packages/server/src/robot_jsonrpcremote_server/_runner.py` (the unreachable `ResultWriter` branch) and the help text of `--outputdir` in `__main__.py`.
- **Workflow:** `openspec/config.yaml`.
- **Order:** after `add-ci-version-matrix`, so the site's jobs run on the new matrix from the start; before `fix-keyword-failure-reporting` and every later change, which document their user-visible behavior on the site.
