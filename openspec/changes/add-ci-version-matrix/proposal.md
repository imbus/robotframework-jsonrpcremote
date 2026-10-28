# Proposal

## Why

CI runs every test on Python 3.10 only, the version pinned in `.python-version`, and only with the Robot Framework version locked in `uv.lock`. Problems that depend on the version never show up there:

- the session-end stall fixed by `fix-client-session-end` only happens on Python 3.13 and later;
- the rejection of `int | None` in `validate_types`, fixed by `fix-json-helpers`, only happens on Python 3.10 to 3.13;
- the declared Robot Framework minimum drifted to 7.4 unnoticed (`fix-robot-framework-compatibility`).

On 2026-10-27 the unit tests and Robot suites passed locally on Python 3.10, 3.11, 3.12, 3.13, 3.14, 3.15.0 and the free-threaded 3.14t, but nothing keeps it that way. The package metadata also lacks the classifier for Python 3.15, and the dev dependency `robotremoteserver` is used nowhere in the repository. Coverage is not measured in CI at all; locally it is 80 % with the unit tests and 85 % together with the Robot suites.

Found in the project review of 2026-10-27 (items TEST-2, BUILD-2 and TEST-7).

## What Changes

- **Python versions:** the test job runs the oldest and the newest supported Python version on all three operating systems, and the versions in between and the free-threaded build on Linux.
- **Robot Framework minimum:** one job runs the unit tests and the Robot suites with the oldest Robot Framework version the packages declare.
- **Coverage:** one job measures line and branch coverage of the unit tests and the Robot suites, including the server processes the suites start, and publishes it as a report without a threshold.
- **Metadata:** the four `pyproject.toml` files gain the classifier for Python 3.15, and the unused dev dependency `robotremoteserver` is removed.
- No product code and no behavior change, so the change has no spec delta (`skip_specs: true`).

Assumptions recorded for review:

- Python 3.10 and 3.15 run on Linux, macOS and Windows; 3.11, 3.12, 3.13, 3.14 and 3.14t on Linux only.
- The job with the Robot Framework minimum runs on Linux with Python 3.10.
- The coverage report is informational; it does not fail the build.
- `robotremoteserver` is removed instead of being kept for a later benchmark against Robot Framework's classic `Remote` library.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The change sets `skip_specs: true`.

## Impact

- **CI:** `.github/workflows/ci.yml`: Python matrix, a job for the Robot Framework minimum, a coverage job. Each job keeps running its Robot suites one after another, because they use fixed ports.
- **Build:** the `pyproject.toml` files and `uv.lock`; coverage configuration for the server subprocesses (coverage.py 7.10 or later).
- **Verification:** the workflow can only be checked on GitHub after a push; locally, the same commands run in one environment per Python version.
- **Order:** after `fix-robot-framework-compatibility`, otherwise the job with the Robot Framework minimum fails, and after `fix-client-session-end`, otherwise the stall slows down the jobs on Python 3.13 and later.
