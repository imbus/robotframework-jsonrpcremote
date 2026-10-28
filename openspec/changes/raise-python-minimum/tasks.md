# Tasks

## 1. Minimum version

- [ ] 1.1 Set `requires-python = ">=3.12"` in `pyproject.toml`, `packages/jsonrpcpeer/pyproject.toml`, `packages/protocol/pyproject.toml`, `packages/server/pyproject.toml` and `examples/simple-robot-jsonrpcserver/pyproject.toml`, and remove the classifiers `Programming Language :: Python :: 3.10` and `3.11` from the four files that have them. Verify with `git grep -n -E 'requires-python|Python :: 3\.1[01]' -- '*.toml' ':!uv.lock'` that every `requires-python` says `>=3.12` and no classifier for 3.10 or 3.11 is left
- [ ] 1.2 Pin `3.12` in `.python-version`, set `target-version = "py312"` under `[tool.ruff]` and `python_version = "3.12"` under `[tool.mypy]` in `pyproject.toml`. Run `uv lock`, then `uv sync --all-extras --all-packages --dev`, which recreates `.venv` with 3.12. Verify that `.venv/bin/python -V` reports 3.12, and that `git diff uv.lock` only removes entries and markers for Python before 3.12 and changes the version of no package that stays
- [ ] 1.3 Change the Python requirement to 3.12 in `README.md` ("Requirements"), `packages/server/README.md` and the prerequisites of `CONTRIBUTING.md`. Verify that `git grep -n -E '3\.10|3\.11' -- ':!uv.lock' ':!openspec'` finds nothing

## 2. Integration checks

- [ ] 2.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass on 3.12
- [ ] 2.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass on 3.12
- [ ] 2.3 Run `uv build --all-packages`; verify that the metadata of every wheel in `dist/` states `Requires-Python: >=3.12` and no classifier for 3.10 or 3.11
- [ ] 2.4 Commit the build files, the docs, this `tasks.md` and the proposal as one signed commit on `main` (`git commit -S`): subject `chore(build): require Python 3.12`, a body that explains the end of life of 3.10, the asyncio behavior that the project environment on 3.10 hid, that no code changes, and that 0.2.0 stays available for 3.10 and 3.11, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`; it has no delta specs.
- Commit the archive as its own signed commit: `docs(openspec): archive raise-python-minimum`, then run `uv run ruff format --check .`.
- Update the plan of `fix-peer-lifecycle` with `/opsx:update` to the new minimum before its plan commit: the project environment and CI run 3.12, the start-and-stop test can bound its wait with `asyncio.timeout`, and the extra local run is needed on 3.14 only.
