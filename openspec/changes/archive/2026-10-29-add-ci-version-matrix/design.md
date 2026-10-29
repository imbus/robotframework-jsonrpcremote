# Design

## Context

See proposal.md for the motivation and the decisions confirmed on 2026-10-29.

**CI today** (`.github/workflows/ci.yml`):

- A `lint` job on Linux runs `ruff check`, `ruff format --check` and `mypy`.
- A `test` job runs on `ubuntu-latest`, `macos-latest` and `windows-latest` with `fail-fast: false`. It installs uv with `astral-sh/setup-uv@v8.1.0`, runs `uv sync --all-packages`, the unit tests with `uv run --all-packages pytest` and the Robot suites with `uv run --all-packages robotcode run`, and uploads `results/` as `robot-results-<os>`.
- Every job uses the Python from `.python-version`, 3.12, and the Robot Framework version from `uv.lock`.

**What the tests need:** the Robot suites start their servers on fixed ports from 8271 to 8279, so the suites of one job run one after another; separate jobs run on separate runners and do not collide. `robot.toml` excludes the suites tagged `posix`, among them the stdio suites, on Windows, because the server supports stdio on POSIX only, and the suite tagged `windows` elsewhere.

**Tools** (checked on 2026-10-29):

- The input `python-version` of `astral-sh/setup-uv` sets `UV_PYTHON` for the rest of the job, which overrides `.python-version`; the pinned v8.1.0 has it.
- `uv run --with "robotframework==7.2"` layers that version over the project environment. Robot Framework 7.2 is then the one imported in the command, in subprocesses started with `sys.executable`, and in the `pytest` and `robotcode` scripts, which uv runs with the overlay's interpreter.

## Goals / Non-Goals

**Goals:**

- Every push runs the unit tests and the Robot suites on each supported Python version and on each operating system, and once per operating system with the Robot Framework minimum.

**Non-Goals:**

- Coverage in CI; it is measured locally when the changes that add tests are planned.
- Linting on more than one Python version: `ruff` and `mypy` target 3.12.
- Free-threaded builds.

## Decisions

### 1. The Python axis comes from `setup-uv`'s `python-version` input

The `test` job gets a matrix `python: ["3.12", "3.13", "3.14", "3.15"]` next to `os`, and passes it to `astral-sh/setup-uv` as `python-version`. Every later `uv` command uses that version.

- **Alternative:** `--python <version>` on each `uv` command. The same effect, but a forgotten option recreates the environment with 3.12.
- The uploaded Robot results get the Python version in their name, `robot-results-<os>-<python>`, because artifact names must be unique within a run.

### 2. The Robot Framework minimum is layered over the project with `uv run --with`

A job `test-robot-framework-minimum` runs on the three operating systems with the Python from `.python-version`, 3.12, so that it follows a raised Python minimum on its own. It syncs as the `test` job does, and runs the unit tests and the Robot suites with `uv run --all-packages --with "robotframework==${{ env.ROBOT_FRAMEWORK_MINIMUM }}"`. `ROBOT_FRAMEWORK_MINIMUM` is set once for the job, with a comment that it must match the `robotframework>=` requirement in `pyproject.toml` and `packages/server/pyproject.toml`. GitHub replaces the expression before any shell runs, so it works with PowerShell on Windows as well.

- **Alternative:** install the version into `.venv` with `uv pip install` and run with `uv run --no-sync`. More steps for the same result.
- **Alternative:** read the minimum from `pyproject.toml` in the job. It would follow a raised minimum on its own, but needs a script per platform; a raise changes one more line instead.

### 3. Every job gets a time limit

Each job gets `timeout-minutes: 20`. A hang like the one `fix-client-session-end` fixed would otherwise hold a runner for GitHub's default of six hours, once per affected job.

## Risks / Trade-offs

- **[More jobs per push]** 12 test jobs, 3 jobs for the minimum and the lint job instead of four jobs. → They run in parallel; `fail-fast: false` keeps one failing version from hiding the others.
- **[The minimum in the workflow and in `pyproject.toml` drift apart]** → The comment next to `ROBOT_FRAMEWORK_MINIMUM` names both files; the tasks of a change that raises the minimum update it.
- **[Python 3.15 on the runners]** uv downloads the interpreter, so a runner image without it still works. → If a download fails, only that job fails.
- **[A timing-dependent test fails on one runner]** More runs make rare races visible. → Intended; a failure names its job, so the version and the operating system are known.
- **[The workflow can only be checked on GitHub]** → The same commands run locally in one environment per version before the push; the first run after the push is part of the change.
