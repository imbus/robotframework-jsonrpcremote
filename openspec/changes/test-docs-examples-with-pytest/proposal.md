# Proposal

## Why

Each example of the documentation site has a `run.sh` that repeats the commands of its page in Bash, and the docs workflow runs them on Linux only. The commands on the pages are the same on every platform, so a script per example adds nothing for readers, and it leaves macOS and Windows unchecked: there, the scripts would need Git Bash, and their cleanup ends with exit code 143, because `kill` is a hard stop on Windows. A test in the normal test suite checks the examples on all three systems instead, with the Python versions and the Robot Framework minimum of the CI matrix (backlog DOC-7; Daniel's decision on 2026-11-07).

## What Changes

- **Removed:** the `run.sh` of every example in `docs/examples/<name>/`, and the job `examples` in `.github/workflows/docs.yml`; the job that deploys the site then waits for the build only.
- **New test:** `tests/test_docs_examples.py` runs each example as its page describes it: it starts the server where the page starts one, waits until the server accepts connections, runs `robot` with the suites of the example, checks the results that the scripts check today, such as the statuses and messages of the failures example, and stops the server. It runs in the jobs of `.github/workflows/ci.yml` on Linux, macOS and Windows.
- **Container example:** it needs docker with Linux containers. It runs where docker can run Linux containers, skips elsewhere, and fails instead of skipping on Linux in CI, as the test of Node's default pipes does without `node`.
- **Contributor docs:** `AGENTS.md` and `CONTRIBUTING.md` name the test instead of the scripts, and the comment in `docs/examples/container/Dockerfile` names the test instead of the CI of the documentation.
- **Not in this change:** Windows equivalents of the scripts, which are not wanted, and changes to the pages, whose commands stay as they are.
- No product behavior changes, so the change has no spec delta (`skip_specs: true`).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._

## Impact

- **Removed files:** `docs/examples/*/run.sh` (eight scripts).
- **New file:** `tests/test_docs_examples.py`.
- **CI:** `.github/workflows/docs.yml` loses the job `examples`; `.github/workflows/ci.yml` runs the examples with the other unit tests, so every Python version, every operating system and the Robot Framework minimum run them. The container example builds an image in each Linux job.
- **Docs for contributors:** `AGENTS.md`, `CONTRIBUTING.md`, the comment in `docs/examples/container/Dockerfile`.
- **Pages:** unchanged.
- **Deploy:** the site no longer waits for the examples; a broken example fails the CI workflow of the same push instead.
