# Design

## Context

See proposal.md for the motivation. Today, `docs/examples/<name>/run.sh` changes into the folder of its example, starts a server in the background where the page does, waits until `127.0.0.1:8271` accepts connections, runs `robot`, and stops the server in an exit trap with `kill`. The failures example also checks `output.xml` with inline Python. The job `examples` of `.github/workflows/docs.yml` runs every script with `uv run --all-packages bash` on Ubuntu, and the deploy job waits for it.

Measured on 2026-11-07:

- **Linux:** each example takes 0 to 3 seconds, the container example 5 seconds with a warm image cache (podman as `docker`).
- **Windows VM, with Git Bash:** all suites and checks pass, but the five scripts that stop a server end with exit code 143, because `kill` is a hard stop there. Five servers in a row bound port 8271 without a conflict, so stopping the uv launcher of `robot-jsonrpcremote-server.exe` also ends the server behind it.
- **The pages:** they do not show every command. `connect-retry` and `own-server` show none, `failures` and `rpc-scope` only the server. So the test follows what the pages describe and the scripts do, and does not parse the pages.

## Goals / Non-Goals

**Goals:**

- Every example runs in the jobs of `ci.yml`, on Linux, macOS and Windows, with every Python version of the matrix and with the Robot Framework minimum.
- The test runs the commands as a reader types them: the console scripts `robot`, `robot-jsonrpcremote-server` and `simple-robot-jsonrpcserver`, in the folder of the example.
- A failure names the example and shows what its server wrote.

**Non-Goals:**

- Checking that each command appears verbatim on its page.
- Changes to the pages or to the example files, except the comment in the Dockerfile.

## Decisions

### 1. One test function per example, with shared helpers

The examples differ too much for one parametrized test: `connect-retry` starts the suite before the server, `failures` runs its suite twice and checks messages, `own-server` runs two suites against a hand-written server, `stdio` needs no server, and `container` uses docker. So `tests/test_docs_examples.py` has one test per example, built from three helpers:

- `_server(command, folder)`: a context manager that starts the command in the folder, writes its output to a file of the test, waits up to 10 seconds until `127.0.0.1:8271` accepts connections, and fails with that output if the process ends before. On exit, it stops the server (decision 4).
- `_robot(arguments, folder)`: runs `robot` in the folder with the outputs in the test's temporary folder (decision 3), and returns its exit code and the result read with `robot.api.ExecutionResult`.
- `_command(name)`: finds a console script (decision 2).

**Alternative:** a table of examples with one parametrized test. It would need a special case for four of the eight examples.

### 2. The console scripts, found next to the interpreter first

The test looks for each console script in the folder of `sys.executable` first, then on `PATH`. So it works:

- under `uv run --all-packages pytest`, where both are the project's environment;
- under `uv run --with "robotframework==7.2"`, where `robot` of the minimum lies in the overlay environment and the server's script in the project's environment, both on `PATH`;
- with the interpreter of an environment called directly, as in the recipe for several Python versions, where `PATH` may not name the environment.

**Alternative:** `python -m robot` and `python -m robot_jsonrpcremote_server`. It differs from the commands on the pages and leaves the console scripts untested.

### 3. Outputs in the test's temporary folder, through `ROBOT_OPTIONS`

`robot` writes `output.xml`, `log.html` and `report.html` to the current folder, which is the example's. The test sets the environment variable `ROBOT_OPTIONS` to `--outputdir <tmp_path>`, so the command stays as on the page and the folders of the examples stay clean. The failures example adds `--loglevel DEBUG`, which its checks need, as its script does.

### 4. Stopping a server, and waiting for its port

On exit, `_server` calls `terminate()`: SIGTERM on POSIX, which the server handles as a graceful stop, and a hard stop on Windows. It waits up to 10 seconds, then kills, and then waits until the port refuses connections, so that the next example can bind it. The exit code of the server is not checked, because on Windows a hard stop gives 1, and the example server does not handle SIGTERM.

### 5. The container example runs where docker can run Linux containers

- **Linux:** it runs if `docker` is on `PATH`. In CI, where `CI` is set, a missing `docker` fails the test instead of skipping it, as the test of Node's default pipes does without `node`. The Linux runners of GitHub have docker.
- **macOS and Windows:** it runs only if `docker info` reports Linux containers, as Docker Desktop can; otherwise it skips. The runners of GitHub have no docker on macOS, and only Windows containers on Windows; the Windows test VM has none.
- **Steps, as in the script:** build the wheels of the current code with `uv build --package <package> --wheel` into `docs/examples/container/wheels`, which `.gitignore` covers and the Dockerfile reads from its build context; build the image with `--build-arg PACKAGES=/context/wheels/*.whl`; start the container as the page does; wait up to 30 seconds for `Server is up and running` in `docker logs`; run the suite of Getting started against it; stop the container in any case.
- **Cost:** each Linux job of the matrix builds the image without a cache, about a minute more per job.

**Alternative:** run it in one job only, through a switch in `ci.yml`. It saves the builds, but every other example runs in all jobs, and a switch is one more thing to keep in sync.

### 6. The docs workflow keeps only the build and the deploy

The job `examples` goes away, and `deploy` needs `build` only. The examples run in the CI workflow, which runs on the same pushes and pull requests.

**Alternative:** keep a job in `docs.yml` that runs `pytest tests/test_docs_examples.py`, so that the deploy still waits for the examples. It runs every example a second time on Linux; the red CI of the same push already shows a broken example.

## Risks / Trade-offs

- [The site deploys even if an example is broken] → The CI workflow of the same push fails, and the next push deploys the fixed example.
- [Port 8271 is in use on a developer's machine] → The server fails to start and the test fails with its message. The pages use that port, so the test does too.
- [The examples now run against the Robot Framework minimum, where a message of the failures example could differ] → That is a check the scripts never made. A difference shows in the minimum jobs and gets fixed in the example or its page.
- [A server stopped hard on Windows leaves a server behind its launcher] → Measured on the VM: the launcher takes its server along. The test also waits until the port is free before the next example.
- [A container of an earlier run still holds the name `my-library-server`] → The script had the same name; `docker run --rm` and the stop in the cleanup remove it. A run that was killed can leave it, as with the script.

## Migration Plan

None for users. Contributors run `uv run --all-packages pytest tests/test_docs_examples.py` instead of the scripts, as `AGENTS.md` and `CONTRIBUTING.md` will say.
