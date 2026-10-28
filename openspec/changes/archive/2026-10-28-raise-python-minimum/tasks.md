# Tasks

## 1. Minimum version

- [x] 1.1 Set `requires-python = ">=3.12"` in `pyproject.toml`, `packages/jsonrpcpeer/pyproject.toml`, `packages/protocol/pyproject.toml`, `packages/server/pyproject.toml` and `examples/simple-robot-jsonrpcserver/pyproject.toml`, and remove the classifiers `Programming Language :: Python :: 3.10` and `3.11` from the four files that have them. Verify with `git grep -n -E 'requires-python|Python :: 3\.1[01]' -- '*.toml' ':!uv.lock'` that every `requires-python` says `>=3.12` and no classifier for 3.10 or 3.11 is left
- [x] 1.2 Pin `3.12` in `.python-version`, set `target-version = "py312"` under `[tool.ruff]` and `python_version = "3.12"` under `[tool.mypy]` in `pyproject.toml`. Run `uv lock`, then `uv sync --all-extras --all-packages --dev`, which recreates `.venv` with 3.12. Verify that `.venv/bin/python -V` reports 3.12, and that `git diff uv.lock` only removes entries and markers for Python before 3.12 and changes the version of no package that stays
- [x] 1.3 Change the Python requirement to 3.12 in `README.md` ("Requirements"), `packages/server/README.md` and the prerequisites of `CONTRIBUTING.md`. Verify that `git grep -n -E '3\.10|3\.11' -- ':!uv.lock' ':!openspec'` finds nothing
- [x] 1.4 Add the classifier `Programming Language :: Python :: 3.15` after the one for 3.14 in the four files that have classifiers. Verify with `git grep -n -E 'Python :: 3\.1[0-9]' -- '*.toml' ':!uv.lock'` that each of them lists 3.12 to 3.15, and that `uv lock --check` passes

## 2. Integration checks

- [x] 2.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass on 3.12
- [x] 2.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass on 3.12
- [x] 2.3 Run `uv build --all-packages` into a scratch directory with `-o`, so the artifacts in `dist/` stay as they are; verify that the metadata of every wheel built states `Requires-Python: >=3.12`, no classifier for 3.10 or 3.11, and, where the package has classifiers, the one for 3.15
- [x] 2.4 Run the unit tests and the Robot suites on Python 3.15 in an environment outside the repository (`UV_PROJECT_ENVIRONMENT=<dir>/venv uv sync --frozen --all-extras --all-packages --dev --python 3.15`, then `<venv>/bin/python -m pytest` and `<venv>/bin/robotcode run -d <dir>/results`). Verify that all pass, and that any warning comes from a defect that another change covers or that is recorded for one
- [x] 2.5 Commit the build files, the docs, this `tasks.md` and the proposal as one signed commit on `main` (`git commit -S`): subject `chore(build): require Python 3.12`, a body that explains the end of life of 3.10, the asyncio behavior that the project environment on 3.10 hid, that no code changes, the classifier for 3.15 after the runs on 3.15, and that 0.2.0 stays available for 3.10 and 3.11, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`; it has no delta specs.
- Commit the archive as its own signed commit: `docs(openspec): archive raise-python-minimum`, then run `uv run ruff format --check .`.
- Update the plan of `fix-peer-lifecycle` with `/opsx:update` to the new minimum, as a commit of its own: the project environment and CI run 3.12, the start-and-stop test can bound its wait with `asyncio.timeout`, and the extra local run is needed on 3.14 only.
