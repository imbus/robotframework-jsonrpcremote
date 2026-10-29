# Proposal

## Why

CI runs every test on Python 3.12 only, the version pinned in `.python-version`, and only with the Robot Framework version locked in `uv.lock`. Problems that depend on the version never show up there. The review follow-up series found three of them locally:

- the session-end stall, fixed by `fix-client-session-end`, which showed mostly on Python 3.14 and 3.15;
- the rejection of `int | None` in `validate_types`, still open for `fix-json-helpers`, which happens on Python 3.12 and 3.13 only;
- the declared Robot Framework minimum, which had drifted to 7.4 unnoticed until `fix-robot-framework-compatibility` raised it to 7.2.

The unit tests and Robot suites passed locally on Python 3.12, 3.14 and 3.15 on 2026-10-29, but nothing keeps it that way. The dev dependency `robotremoteserver` is used nowhere in the repository.

Found in the project review of 2026-10-27 (items TEST-2 and BUILD-2). The classifier for Python 3.15 from BUILD-2 came with `raise-python-minimum`. Coverage in CI (TEST-7) is left out: it is measured locally when the changes that add tests are planned.

## What Changes

- **Python versions:** the test job runs Python 3.12, 3.13, 3.14 and 3.15 on Linux, macOS and Windows. Free-threaded builds are not tested.
- **Robot Framework minimum:** one job per operating system runs the unit tests and the Robot suites with the oldest Robot Framework version the packages declare, on Python 3.12.
- **Dependencies:** the unused dev dependency `robotremoteserver` is removed.
- No product code and no behavior change, so the change has no spec delta (`skip_specs: true`).

Decisions confirmed on 2026-10-29:

- Python 3.12 to 3.15 on all three operating systems, without a free-threaded build.
- The job with the Robot Framework minimum runs on Linux, macOS and Windows with Python 3.12.
- Coverage is not measured in CI.
- `robotremoteserver` is removed; a benchmark against Robot Framework's classic `Remote` library (PERF-1) can add it again.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **CI:** `.github/workflows/ci.yml`: a Python axis for the test job and a job for the Robot Framework minimum per operating system. Each job keeps running its Robot suites one after another, because they use fixed ports. On Windows the stdio suites stay excluded, because the server supports stdio on POSIX only.
- **Build:** `pyproject.toml` and `uv.lock`: `robotremoteserver` goes.
- **Verification:** the workflow can only be checked on GitHub after a push; locally, the same commands run in one environment per Python version.
- **Order:** after `fix-robot-framework-compatibility` and `fix-client-session-end`, which are done. The push after this change lets the new matrix run once.
