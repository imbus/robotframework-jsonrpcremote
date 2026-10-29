# Tasks

## 1. Layout

- [ ] 1.1 Move `tests/robot/` to `atests/` and every file of `tests/unit/` to `tests/` with `git mv`, and remove the then empty `tests/unit/`, including its untracked `__pycache__`. Verify that `git status` lists only renames, and that `tests/` holds the unit tests with `fake_server.py` and `atests/` the Robot suites, their helper libraries and `_nested/`
- [ ] 1.2 In `pyproject.toml`, set `testpaths = ["tests"]` for pytest and replace `tests/unit` with `tests` in `files` and `mypy_path` of mypy; in `robot.toml`, set `paths = ["atests"]`. Verify that `uv run --all-packages pytest --collect-only -q` collects 168 tests as before the move, that `uv run mypy` checks 30 source files as before, and that `uv run robocop check` reports the same 49 issues as before
- [ ] 1.3 Replace `tests/unit` and `tests/robot` with the new paths in `AGENTS.md` (orientation, task routing, commands), `CONTRIBUTING.md` (repository layout, running tests), `README.md` and the docstring of `tests/test_client_connection.py`. Verify that `git grep -n -E 'tests/(unit|robot)' -- ':!openspec' ':!uv.lock'` finds nothing

## 2. Testing rule

- [ ] 2.1 Write the rule on which tests a change needs, naming `tests/` and `atests/`: three rules under `rules.tasks` in `openspec/config.yaml`, a bullet under "Tests" in `AGENTS.md` and the paragraph "Which tests a change needs" under "Running Tests" in `CONTRIBUTING.md`. Verify that `openspec instructions tasks --change fix-client-session-end --json` returns the three rules and that the three texts state the same rule

## 3. Plans of the active changes

- [ ] 3.1 Replace `tests/unit/` with `tests/` and `tests/robot/` with `atests/` in the planning artifacts of the active OpenSpec changes; leave `openspec/changes/archive/` unchanged. Verify that `git grep -n -E 'tests/(unit|robot)' -- openspec ':!openspec/changes/archive'` finds nothing and that `openspec validate fix-peer-lifecycle --strict` passes
- [ ] 3.2 Add to task 5.3 of `fix-peer-lifecycle` why it adds no Robot test, as the rule from 2.1 asks: what it changes cannot be observed from Robot Framework, and the cancelled close depends on timing. Verify that `openspec validate fix-peer-lifecycle --strict` passes

## 4. Integration checks

- [ ] 4.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass with 167 passed and 1 skipped, as before the move
- [ ] 4.2 Run `uv run --all-packages robotcode run`; verify all 53 Robot tests pass and the output lands in `results/`. This change adds no Robot test: it moves files and changes no behavior that Robot Framework could observe
- [ ] 4.3 Commit the moves, configuration, docs, rules, the updated plans, this `tasks.md` and the proposal as one signed commit on `main` (`git commit -S`): subject `refactor(tests): move unit tests to tests/ and Robot tests to atests/`, a body that explains the Robot Framework convention, the testing rule and that no test changes, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Archive the change with `/opsx:archive`; it has no delta specs.
- Commit the archive as its own signed commit: `docs(openspec): archive reorganize-test-directories`, then run `uv run ruff format --check .`.
- Continue with `/opsx:apply fix-peer-lifecycle`.
