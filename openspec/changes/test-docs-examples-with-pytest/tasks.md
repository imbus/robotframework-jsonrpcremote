# Tasks

Every new test is run once against an example without the part that the test covers, and must fail there: a suite that expects another result, a server that does not start, or an expected message that differs. Runs on the Windows test VM have a hard time limit, and the copy there has no `__pycache__`.

## 1. The test of the examples

- [ ] 1.1 Add `tests/test_docs_examples.py` with the helpers `_command()`, `_server()` and `_robot()` (design decisions 1 to 4), and one test each for `getting-started`, `failures`, `own-server`, `rpc-scope`, `several-libraries`, `connect-retry` and `stdio`, with the checks of their scripts: the suites pass, and for `failures` the statuses and messages of its five tests, the traceback at `DEBUG` level, the server running on after the fatal failure, and the message of the refused import. Verify with `uv run --all-packages pytest tests/test_docs_examples.py` on Linux and on the Windows VM, that the examples leave no `output.xml`, `log.html` or `report.html` in their folders, that port 8271 is free after each test, and that each test fails against its example broken as described above. It adds no Robot test, because it changes no behavior of the library: the examples are Robot suites already, and the test runs them.
- [ ] 1.2 Add the test of the `container` example (design decision 5). Verify that it passes on Linux with docker (podman locally), that it skips on the Windows VM, which has no docker, with a reason that names docker, and that with `CI=true` and no `docker` on `PATH` on Linux it fails instead of skipping. Verify that it fails when the image cannot be built, for example with a wrong package name. It adds no Robot test, for the reason of 1.1.

## 2. Remove the scripts

- [ ] 2.1 Remove `docs/examples/*/run.sh` and the job `examples` from `.github/workflows/docs.yml`, and let the job `deploy` need `build` only (design decision 6). Verify that `git ls-files docs/examples` lists no `run.sh`, and that the workflow file still parses as YAML with the jobs `build` and `deploy`.
- [ ] 2.2 Name the test instead of the scripts in `AGENTS.md` (the task routing of the documentation site and the common command for one example), in `CONTRIBUTING.md` (section Improving The Documentation) and in the comment of `docs/examples/container/Dockerfile`. Verify that `git grep run.sh -- ':!openspec/changes/archive'` finds no reference to the scripts, and that the documented command `uv run --all-packages pytest tests/test_docs_examples.py` runs as written. The pages of the site name no script, so they stay as they are.

## 3. Integration checks

- [ ] 3.1 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run mypy --platform win32` and `uv run --all-packages pytest`; verify all pass.
- [ ] 3.2 Run `uv run --all-packages robotcode run` as a regression check, and `uv run --all-packages --with "robotframework==7.2"` with `pytest` and with `robotcode run`; verify all pass, the examples under Robot Framework 7.2 included.
- [ ] 3.3 On the Windows VM, with hard time limits, run the unit tests with Python 3.12 and 3.14t, and with `uv run --with "robotframework==7.2"`; verify all pass, the container test skips, and no process of the examples stays behind.
- [ ] 3.4 Run `npm ci` and `npm run build` in `docs/`; verify the site builds and its internal links are valid.
- [ ] 3.5 Commit the change, this `tasks.md` and the planning artifacts as one signed commit on `main` (`git commit -S`), staging only the paths of this change:
  - **Subject:** `test(docs): run the examples of the site with pytest on every system`.
  - **Body:** explains why the scripts go, that the commands are the same on every system, where the examples run now, and how the container example decides whether it runs.
  - **No** `Refs` and no co-author.

  Verify with `uv run --all-packages cz check --rev-range HEAD~1..HEAD` and `git log --show-signature -1`.

## Workflow follow-up

- Daniel pushes `main`; check that the CI runs the tests of the examples on Linux, macOS and Windows and not skipped, except the container test outside Linux, and that the docs workflow builds and deploys the site without the job `examples`.
- Archive the change with `/opsx:archive`; it has no delta specs (`skip_specs: true`). Commit the archive as `docs(openspec): archive test-docs-examples-with-pytest`.
- Mark DOC-7 as done in `playground/anforderungen-und-ideen.md`.
