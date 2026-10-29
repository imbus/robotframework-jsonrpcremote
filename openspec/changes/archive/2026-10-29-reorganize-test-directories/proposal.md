# Proposal

## Why

Unit tests and Robot Framework tests share one directory: `tests/unit/` and `tests/robot/`. Projects in the Robot Framework world keep their Robot tests in a top-level directory of their own: `atest/` in Robot Framework itself, SeleniumLibrary and Browser, `atests/` in RequestsLibrary. Contributors from that world look for them there, and each tool then points at one directory: pytest at the unit tests, robotcode and robocop at the Robot tests.

Which tests a change needs is not written down either. The contribution guide says to add unit tests for any Python change and to run the Robot suites, but not when a change needs a Robot test of its own. So far that was only the practice of the review follow-up series.

Now is the time: the plans of the series name test paths in about twenty places, and `fix-peer-lifecycle`, the next change to be implemented, adds tests in three files.

## What Changes

- **Layout:** the unit tests move from `tests/unit/` to `tests/`, the Robot suites with their helper libraries and `_nested/` from `tests/robot/` to `atests/`. Robot output stays in `results/`.
- **Configuration:** `testpaths` of pytest and `files` and `mypy_path` of mypy in `pyproject.toml`, `paths` in `robot.toml`. CI and the VS Code settings need no change; they name no test path or already name `tests`.
- **Testing rule:** `openspec/config.yaml` gets rules for tasks, and `AGENTS.md` and `CONTRIBUTING.md` a rule on which tests a change needs: unit tests for every Python change; a Robot test when the change can be observed from Robot Framework, such as keyword calls with their arguments and results, log messages, execution errors, the library import, Libdoc or the output files, and otherwise a reason; the unit tests and all Robot suites run for every change.
- **Docs:** `AGENTS.md`, `CONTRIBUTING.md`, `README.md` and a docstring in a unit test name the new paths.
- **Plans:** the active OpenSpec changes name the new paths, and the tasks of `fix-peer-lifecycle` say why it adds no Robot test. Archived changes stay as they are.
- No product code and no behavior change, so the change adds no Robot test and has no spec delta (`skip_specs: true`).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **Tests:** every file in `tests/unit/` and `tests/robot/` moves; no test changes, except the path from `tests/test_client_connection.py` to the Robot helper libraries that its stdio tests use.
- **Configuration:** `pyproject.toml`, `robot.toml`.
- **Docs and rules:** `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `openspec/config.yaml`.
- **Plans:** the proposals of the active changes that name test paths, and proposal, design and tasks of `fix-peer-lifecycle`.
- **Contributors:** local run configurations that point at `tests/unit` or `tests/robot` need the new path.
- **Order:** inserted after `raise-python-minimum` and before the implementation of `fix-peer-lifecycle`, so its tests land in their final place.
