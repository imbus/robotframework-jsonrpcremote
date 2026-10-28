# Proposal

## Why

All packages declare `requires-python = ">=3.10"`, and `.python-version` pins 3.10, so the project environment and CI run the oldest supported version. Two reasons to raise the minimum to Python 3.12 now:

- **Python 3.10 reached its end of life in October 2026.**
- **asyncio behaves differently before 3.12, and the default test run only sees the old behavior.** Before 3.12, `asyncio.wait_for` runs the awaited coroutine in a task of its own; while planning `fix-peer-lifecycle`, this hid the hang of `stop()` right after `start()` on 3.10. Deprecations that become errors in 3.14, such as creating an `asyncio.Future` without a running loop, only warn from 3.12 on. With the project environment on 3.10, a plain `pytest` run shows neither.

Raising the minimum costs no code: there are no version checks and no backports, and `ruff` and `mypy` with Python 3.12 as their target report nothing (checked on 2026-10-28). The unit tests and Robot suites passed on 3.12 in the review run of 2026-10-27. The project has no 1.0 release yet, so the change is not marked as breaking; users on 3.10 and 3.11 keep 0.2.0, which stays installable from PyPI.

## What Changes

- **Minimum version:** Python 3.12 in `requires-python` of the five `pyproject.toml` files (the client, `jsonrpcpeer`, the protocol, the server, the example); the classifiers for 3.10 and 3.11 are removed.
- **Development and CI:** `.python-version` pins 3.12, so the project environment and CI run on 3.12; `ruff` targets `py312` and `mypy` checks against 3.12.
- **Lock file:** `uv.lock` is regenerated and loses the entries and markers for Python before 3.12.
- **Documentation:** the requirement in `README.md`, `packages/server/README.md` and the prerequisites in `CONTRIBUTING.md`.
- **No code change:** newer syntax such as PEP 695 generics is not introduced; `typing_extensions` stays for `TypeForm`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **Build:** the five `pyproject.toml` files, `.python-version`, `uv.lock`.
- **Tooling:** the `ruff` and `mypy` settings in `pyproject.toml`.
- **CI:** no file change; `.github/workflows/ci.yml` follows `.python-version`.
- **Docs:** `README.md`, `packages/server/README.md`, `CONTRIBUTING.md`.
- **Users:** Python 3.10 and 3.11 are no longer supported by new releases.
- **Other changes of the series:** the proposals of `fix-peer-lifecycle` (planned, not yet committed), `add-ci-version-matrix` and `fix-json-helpers` state facts about 3.10 and 3.11, such as the CI version and the matrix. Each is corrected when it is planned or updated; `fix-peer-lifecycle` right after this change.
- **Order:** inserted after `fix-robot-framework-compatibility` and before `fix-peer-lifecycle`, whose tests then run on 3.12 by default; before `add-ci-version-matrix`, which builds its matrix on the minimum.
