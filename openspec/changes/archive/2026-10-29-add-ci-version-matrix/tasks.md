# Tasks

## 1. Dependencies

- [x] 1.1 Remove `robotremoteserver` from the dev dependencies in `pyproject.toml` and run `uv lock`. Verify that `git grep -n robotremoteserver -- ':!openspec'` finds nothing, that `git diff uv.lock` removes only `robotremoteserver` and what nothing else needs, and that `uv sync --all-extras --all-packages --dev` succeeds

## 2. CI workflow

- [x] 2.1 In `.github/workflows/ci.yml`, add `python: ["3.12", "3.13", "3.14", "3.15"]` to the matrix of the `test` job, pass it to `astral-sh/setup-uv` as `python-version`, and put it into the job's name and into the name of the uploaded results, `robot-results-${{ matrix.os }}-${{ matrix.python }}` (design decision 1). Verify locally on Linux that the unit tests and all Robot suites pass on each of the four versions, one after another because of the fixed ports, each in an environment outside the repository (`UV_PROJECT_ENVIRONMENT=<dir>/venv-<version> uv sync --frozen --all-extras --all-packages --dev --python <version>`, then `<venv>/bin/python -m pytest` and `<venv>/bin/robotcode run -d <dir>/results-<version>`)
- [x] 2.2 Add the job `test-robot-framework-minimum` on `ubuntu-latest`, `macos-latest` and `windows-latest` with the Python from `.python-version`, 3.12, and `fail-fast: false`. It sets `ROBOT_FRAMEWORK_MINIMUM: "7.2"` for the job, with a comment that it must match `robotframework>=` in `pyproject.toml` and `packages/server/pyproject.toml`, syncs like the `test` job, runs `uv run --all-packages --with "robotframework==${{ env.ROBOT_FRAMEWORK_MINIMUM }}" pytest` and the same with `robotcode run`, and uploads `results/` as `robot-results-${{ matrix.os }}-robot-framework-minimum` (design decision 2). Verify locally that `uv run --all-packages --with "robotframework==7.2" python -c "import robot; print(robot.version.VERSION)"` prints `7.2`, and that both test commands pass with it
- [x] 2.3 Give every job `timeout-minutes: 20` (design decision 3). Verify by loading the workflow with `uv run python -c` and `yaml.safe_load`: the jobs `lint`, `test` and `test-robot-framework-minimum` each have `timeout-minutes: 20`, the `test` matrix has three operating systems and four Python versions, and the job for the minimum has three operating systems

## 3. Integration checks

- [x] 3.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run --all-packages pytest`; verify all pass
- [x] 3.2 Run `uv run --all-packages robotcode run`; verify all Robot suites pass. This change adds no Robot test and no unit test: it changes CI and a dev dependency, nothing that the tests could observe
- [x] 3.3 Commit the workflow, `pyproject.toml`, `uv.lock`, this `tasks.md` and the updated planning artifacts as one signed commit on `main` (`git commit -S`): subject `chore(build): test Python 3.12 to 3.15 and the Robot Framework minimum in CI`, a body that explains the version-dependent defects CI did not see, the matrix, the job for the minimum with `uv run --with`, the time limits and the removed dependency, without `Refs` and without a co-author; verify with `uv run cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`

## Workflow follow-up

- Push `main` once Daniel agrees, and check the CI run on GitHub: the lint job, 12 test jobs and 3 jobs for the minimum all pass. A failure gets its own fix commit before the archive.
- Archive the change with `/opsx:archive`; it has no delta specs.
- Commit the archive as its own signed commit: `docs(openspec): archive add-ci-version-matrix`, then run `uv run ruff format --check .`.
- Set TEST-2 and BUILD-2 to done in `playground/anforderungen-und-ideen.md`.
