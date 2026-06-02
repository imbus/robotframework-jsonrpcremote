<!-- omit in toc -->
# Contributing to robotframework-jsonrpcremote

First off, thanks for taking the time to contribute!

All types of contributions are encouraged and valued. See the [Table of Contents](#table-of-contents) for different ways to help and details about how this project handles them. Please make sure to read the relevant section before making your contribution. It will make it easier for the maintainers and smooth out the experience for everyone involved.

And if you like the project, but just don't have time to contribute, that's fine. There are other easy ways to support the project and show your appreciation, which we would also be very happy about:
- Star the project
- Refer this project in your project's readme
- Mention the project to your friends/colleagues

<!-- omit in toc -->
## Table of Contents

- [I Have a Question](#i-have-a-question)
- [Project-Wide Rules](#project-wide-rules)
  - [AI and Automated Contributions](#ai-and-automated-contributions)
- [I Want To Contribute](#i-want-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
    - [Development Environment Setup](#development-environment-setup)
    - [Pre-commit Hooks](#pre-commit-hooks)
    - [Project Structure](#project-structure)
    - [Development Workflow](#development-workflow)
    - [Running Tests](#running-tests)
    - [Linting and Type Checking](#linting-and-type-checking)
    - [Building the Packages](#building-the-packages)
    - [Releasing (Maintainers)](#releasing-maintainers)
    - [Pull Request Guidelines](#pull-request-guidelines)
    - [Troubleshooting Development Setup](#troubleshooting-development-setup)
  - [Improving The Documentation](#improving-the-documentation)
- [Styleguides](#styleguides)
  - [Commit Messages](#commit-messages)
  - [Signed Commits Required](#signed-commits-required)


## I Have a Question

If you want to ask a question, we assume that you have read the [README](README.md) and the README files of the relevant packages under [`packages/`](packages).

Before you ask a question, it is best to search the existing [Issues](https://github.com/imbus/robotframework-jsonrpcremote/issues) that might help you. In case you have found a suitable issue and still need clarification, you can write your question in that issue. It is also advisable to search the internet for answers first.

If you then still need clarification, we recommend the following:

- Open an [Issue](https://github.com/imbus/robotframework-jsonrpcremote/issues/new).
- Provide as much context as you can about what you're running into.
- Provide project and platform versions (Python, Robot Framework, OS), depending on what seems relevant.

We will then take care of the issue as soon as possible.

You can also reach the wider Robot Framework community in the [Robot Framework Slack](https://robotframework.slack.com) or the [Robot Framework Forum](https://forum.robotframework.org).

## Project-Wide Rules

These rules apply to all interactions with the project — pull requests, issues, discussions, comments, code review replies, and any other contribution. Please read them before opening a contribution of any kind.

### AI and Automated Contributions

AI-assisted or automated contributions, including agent-generated ones, must follow our [AI and Automated Contribution Policy](AI_POLICY.md). In short: the human submitter must understand, review, test, and maintain the contribution, and must disclose AI or tool assistance in the pull request, issue, or comment.

## I Want To Contribute

> [!IMPORTANT]
> **Legal Notice**
>
> When contributing to this project, you must agree that you have the right to submit the contribution under the project license ([Apache-2.0](LICENSE)).
>
> This means that the contribution was created in whole or in part by you, is based on previous work that you are allowed to submit under a compatible license, or was otherwise lawfully provided to you for contribution.
>
> This corresponds to the spirit of the [Developer Certificate of Origin](https://developercertificate.org/). You are encouraged to add a DCO sign-off to your commits with `git commit -s` — this only adds a `Signed-off-by` trailer and is separate from the cryptographic commit signature (`-S`, GPG/SSH) required by [Signed Commits Required](#signed-commits-required) below.
>
> If AI tools or automated agents were used, you remain the human submitter responsible for the contribution and must follow the [AI and Automated Contribution Policy](AI_POLICY.md).

### Reporting Bugs

<!-- omit in toc -->
#### Before Submitting a Bug Report

A good bug report shouldn't leave others needing to chase you up for more information. Therefore, we ask you to investigate carefully, collect information, and describe the issue in detail. Please complete the following steps in advance to help us fix any potential bug as fast as possible.

- Make sure that you are using the latest version.
- Determine if your bug is really a bug and not an error on your side, e.g. using incompatible environment components/versions. Make sure you have read the [README](README.md). If you are looking for support, you might want to check [this section](#i-have-a-question).
- Check whether there is already a bug report for your problem in the [issue tracker](https://github.com/imbus/robotframework-jsonrpcremote/issues).
- Also search the internet (including Stack Overflow) to see if users outside of GitHub have discussed the issue.
- Collect information about the bug:
  - Stack trace (traceback)
  - OS, platform, and version (Windows, Linux, macOS, x86, ARM)
  - Python and Robot Framework versions, and the server version/implementation you connect to
  - Possibly your input and the output
  - Can you reliably reproduce the issue? Can you also reproduce it with older versions?

<!-- omit in toc -->
#### How Do I Submit a Good Bug Report?

> [!WARNING]
> Never report security-related issues, vulnerabilities, or bugs that include sensitive information in the public issue tracker. Send sensitive bugs by email to <dbiehl@live.de> instead.

We use GitHub issues to track bugs and errors. If you run into an issue with the project:

- Open an [Issue](https://github.com/imbus/robotframework-jsonrpcremote/issues/new). (Since we can't be sure at this point whether it is a bug, please don't label it yet.)
- Explain the behavior you expect and the actual behavior.
- Please provide as much context as possible and describe the *reproduction steps* that someone else can follow to recreate the issue. This usually includes your code. For good bug reports you should isolate the problem and create a reduced test case.
- Provide the information you collected in the previous section.

Once it's filed, the project team will try to reproduce the issue with your provided steps and label it accordingly. Bugs without reproduction steps may be marked as `needs-repro` and will not be addressed until they are reproduced.

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion, **including completely new features and minor improvements to existing functionality**.

<!-- omit in toc -->
#### Before Submitting an Enhancement

- Make sure that you are using the latest version.
- Read the [README](README.md) carefully and find out whether the functionality is already covered.
- Perform a [search](https://github.com/imbus/robotframework-jsonrpcremote/issues) to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.
- Find out whether your idea fits the scope and aims of the project. Keep in mind that we want features that are useful to the majority of users.

<!-- omit in toc -->
#### How Do I Submit a Good Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://github.com/imbus/robotframework-jsonrpcremote/issues).

- Use a **clear and descriptive title** for the issue to identify the suggestion.
- Provide a **step-by-step description of the suggested enhancement** in as much detail as possible.
- **Describe the current behavior** and **explain which behavior you expected to see instead** and why.
- **Explain why this enhancement would be useful** to most users.

### Your First Code Contribution

Welcome to your first code contribution! Here's how to set up your development environment and get started.

#### Development Environment Setup

This project is a [uv](https://github.com/astral-sh/uv) workspace (monorepo). All you need is a recent Python and `uv` — `uv` manages the virtual environment and all dependencies for you.

1. **Prerequisites** (see each tool's site for install instructions):
   - [Python](https://www.python.org/) >= 3.10
   - [uv](https://docs.astral.sh/uv/getting-started/installation/)
   - [Git](https://git-scm.com/)

2. **Setup:**
   ```bash
   git clone git@github.com:imbus/robotframework-jsonrpcremote.git
   cd robotframework-jsonrpcremote
   uv sync --all-extras --all-packages --dev
   ```

   `uv sync` creates a `.venv` and installs the client, all workspace packages (`packages/*`), the example server, and the development tools (pytest, ruff, mypy, robotcode, robocop, pre-commit, commitizen, ...). Prefix commands with `uv run` to run them inside that environment, or activate it with `source .venv/bin/activate`.

3. **Install the pre-commit hooks:**
   ```bash
   uv run pre-commit install
   ```

   This installs the `pre-commit`, `commit-msg`, and `pre-push` git hooks. See [Pre-commit Hooks](#pre-commit-hooks) for what they run.

#### Pre-commit Hooks

The repository ships a [`.pre-commit-config.yaml`](.pre-commit-config.yaml) that runs the same checks locally and automatically that are expected on a pull request:

- **commit-msg:** [commitizen](https://commitizen-tools.github.io/commitizen/) checks that the commit message follows [Conventional Commits](#commit-messages).
- **pre-commit:** Ruff lint (`ruff check`), a Ruff formatting check (`ruff format --check`, which only verifies formatting without changing files), and mypy type checking run on the staged files.
- **pre-push:** commitizen validates the commit messages of the range being pushed.

The local hooks call the project's pinned tools via `uv run`, so they use the same Ruff and mypy versions as everything else in the project. Install the hooks once with `uv run pre-commit install` (see step 3 above). To run all hooks manually against the whole repository:

```bash
uv run pre-commit run --all-files
```

#### Project Structure

The repository is a uv workspace organized into a client library, several supporting packages, examples, and tests:

- **[`src/JsonRpcRemote`](src/JsonRpcRemote)** — the Robot Framework client library (the importable `JsonRpcRemote` library / proxy).
- **[`packages/protocol`](packages/protocol)** — JSON-RPC 2.0 protocol messages, data structures, and types.
- **[`packages/jsonrpcpeer`](packages/jsonrpcpeer)** — an asynchronous JSON-RPC 2.0 peer implementation built on `asyncio`.
- **[`packages/server`](packages/server)** — the server runtime that hosts Robot Framework libraries (`robot-jsonrpcremote-server` CLI).
- **[`examples/`](examples)** — runnable usage examples, e.g. a minimal hand-written server.
- **[`tests/unit`](tests/unit)** — fast unit tests (pytest).
- **[`tests/robot`](tests/robot)** — Robot Framework integration tests; each suite starts its own server.

#### Development Workflow

1. **Create a branch:** `git checkout -b feature/your-feature-name`
2. **Make your changes** following the project's coding standards.
3. **Run the unit tests:** `uv run --all-packages pytest`
4. **Run the integration tests:** `uv run --all-packages robotcode run`
5. **Run linting and type checks:** `uv run ruff check .` and `uv run mypy` (see [Linting and Type Checking](#linting-and-type-checking)).
6. **Fix formatting:** `uv run ruff format .`
7. **Commit your changes** with a descriptive, [Conventional Commits](#commit-messages) message, [cryptographically signed](#signed-commits-required) (`git commit -S`).
8. **Push and create a pull request.**

#### Running Tests

> [!IMPORTANT]
> This is a uv workspace, and `uv sync`/`uv run` operate on the **workspace root** by default. `uv run` also re-syncs the environment *exactly* on each call, which prunes the other workspace members (e.g. the server package). The unit tests import the server package and the robot suites spawn it, so pass `--all-packages` to `uv run` (as below) — or activate the venv (`source .venv/bin/activate`) after `uv sync --all-packages --dev` and call the tools directly. Otherwise you'll get `ModuleNotFoundError: No module named 'robot_jsonrpcremote_server'`.

**Unit tests (pytest):**

```bash
uv run --all-packages pytest
```

`pytest` is configured (in [`pyproject.toml`](pyproject.toml)) to collect from `tests/unit` and runs in asyncio auto mode. To run a single file or test:

```bash
uv run --all-packages pytest tests/unit/test_peer.py
uv run --all-packages pytest tests/unit/test_peer.py::test_name -q
```

**Integration tests (Robot Framework):**

```bash
uv run --all-packages robotcode run
```

This runs the Robot Framework suites under [`tests/robot`](tests/robot) (configured via [`robot.toml`](robot.toml)). Each suite starts and stops its own server, so no separate server process is required. `robotcode run` writes its `output.xml`, `log.html`, and `report.html` to the `results/` directory by default (gitignored).

Run the unit tests on every change; run the integration tests before opening or updating a pull request.

#### Linting and Type Checking

This project uses **Ruff** for linting/formatting and **mypy** (strict) for type checking. Configuration lives in [`pyproject.toml`](pyproject.toml).

**Python style (Ruff):**
```bash
uv run ruff check .            # lint
uv run ruff format --check .   # check formatting (CI-style)
uv run ruff format .           # apply formatting
```

**Type checking (mypy, strict):**
```bash
uv run mypy
```

> The check targets are configured via `files` in `[tool.mypy]` (in [`pyproject.toml`](pyproject.toml)), so `uv run mypy` with no arguments checks the whole project. `pyright` is also available in the dev dependencies for editor integration, but mypy is the authoritative type-check gate.

**Robot Framework style (optional, for `tests/robot`):**
```bash
uv run robocop check     # lint the .robot files
uv run robocop format    # format the .robot files
```

#### Building the Packages

To build the distributable artifacts (wheels and sdists) for the client and all workspace packages, run from the repo root:

```bash
uv build --all-packages
```

The build output is written to the `dist/` directory.

#### Releasing (Maintainers)

Releases are driven by [commitizen](https://commitizen-tools.github.io/commitizen/), which derives the next version from the [Conventional Commits](#commit-messages) made since the last release. The four core packages (client, protocol, peer, server) share a single version: `cz bump` updates the root version, the other package versions, and every `__version__.py` together. The example under [`examples/`](examples) is versioned independently and bumped by hand.

Because the project is still in the `0.x` range (`major_version_zero`), a `feat:` bumps the minor version and a `fix:` bumps the patch version; breaking changes also bump the minor version (not the major).

Preview the next version and the changelog entry without changing anything:

```bash
uv run cz bump --dry-run
```

When you are happy with the preview, perform the bump:

```bash
uv run cz bump
```

This updates the version across all core packages, writes/updates [`CHANGELOG.md`](CHANGELOG.md), creates a `chore(release): ...` commit, and creates a signed, annotated git tag `v<version>`. Review the result, then push the commit together with the tag:

```bash
git push --follow-tags
```

> [!NOTE]
> On the very first bump (no tags yet), commitizen asks "Is this the first tag created?" — answer yes. In a non-interactive shell, pass `--yes`.

#### Pull Request Guidelines

When you open a pull request, GitHub will pre-fill the [pull request template](.github/PULL_REQUEST_TEMPLATE.md). Please keep its checklist intact and tick the boxes that apply.

##### PR Checklist

Before submitting your pull request, make sure that:

- [ ] The change is **focused** on a single concern (no unrelated refactors or formatting noise).
- [ ] **Tests** for the change have been added or updated, and `uv run --all-packages pytest` (plus `uv run --all-packages robotcode run` where relevant) passes locally.
- [ ] **Linting** passes: `uv run ruff check .` and `uv run ruff format --check .`.
- [ ] **Type checking** passes: `uv run mypy`.
- [ ] **Documentation** has been updated where relevant (package READMEs, code comments, main README).
- [ ] **Commits** follow [Conventional Commits](#commit-messages) and are [cryptographically signed](#signed-commits-required) (`git commit -S`, GPG/SSH).
- [ ] **AI / tooling disclosure** is included if AI tools or automated agents were used for a substantial part of the change (see [AI_POLICY.md](AI_POLICY.md)).

##### PR Description

A good PR description:
- Explains **what** changed and **why**.
- References any related issues (e.g. `Fixes #123`).
- Lists any breaking changes explicitly.

##### PR Review Process

- Automated checks must pass (tests, linting, type checking).
- At least one maintainer review is required.
- Address feedback promptly and keep your PR up to date with the `main` branch.

#### Troubleshooting Development Setup

**Common Issues:**

1. **`uv sync` fails or the environment is inconsistent:**
   ```bash
   # Recreate the environment from scratch
   rm -rf .venv
   uv sync --all-extras --all-packages --dev
   ```

2. **Tests fail with `ModuleNotFoundError` for a workspace package (e.g. `robot_jsonrpcremote_server`):**
   - `uv run` targets the workspace root and re-syncs exactly, which prunes the other members. Pass `--all-packages` to the test commands (`uv run --all-packages pytest`, `uv run --all-packages robotcode run`), or activate the venv after `uv sync --all-packages --dev` and run the tools directly.

3. **VS Code doesn't find the interpreter:**
   - Select the `.venv` interpreter via the Command Palette → "Python: Select Interpreter".

### Improving The Documentation

Documentation helps users understand and use the project effectively. Ways you can help:

1. **README files** — the main [README](README.md) and the per-package READMEs under [`packages/`](packages) and [`examples/`](examples).
2. **Code documentation** — docstrings for public classes and functions, inline comments for non-obvious logic, and type hints.

Guidelines:
- **Clear and concise:** write for users of all skill levels.
- **Examples:** include practical, working code examples.
- **Testing:** verify that code examples actually work.

For small fixes, edit the file and submit a pull request. For larger changes, open an issue first to discuss the approach.

## Styleguides
### Commit Messages

Good commit messages help maintain a clean project history. Please follow [Conventional Commits](https://www.conventionalcommits.org/). The format is enforced by the [commitizen](https://commitizen-tools.github.io/commitizen/) `commit-msg` hook (see [Pre-commit Hooks](#pre-commit-hooks)). You can also let commitizen build the message interactively:

```bash
uv run cz commit
```

#### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

#### Types

- **feat:** A new feature
- **fix:** A bug fix
- **docs:** Documentation only changes
- **style:** Changes that do not affect the meaning of the code (white-space, formatting, etc.)
- **refactor:** A code change that neither fixes a bug nor adds a feature
- **perf:** A code change that improves performance
- **test:** Adding missing tests or correcting existing tests
- **chore:** Changes to the build process or auxiliary tools

#### Scope

The scope should indicate the package or area affected:
- **client:** The Robot Framework client library (`src/JsonRpcRemote`)
- **server:** The server runtime (`packages/server`)
- **peer:** The JSON-RPC peer (`packages/jsonrpcpeer`)
- **protocol:** The protocol definitions (`packages/protocol`)
- **examples:** Example servers/clients
- **tests:** Tests
- **docs:** Documentation
- **build:** Build, packaging, or tooling
- **release:** Version bumps (used by `cz bump`)

#### Examples

```
feat(server): forward log messages during keyword execution

Stream Robot Framework log messages from the server to the client
while a keyword is running, so progress is visible in real time.

Closes #42
```

```
fix(client): keep rpc options separate from forwarded library kwargs

Reserved client options were leaking into the keyword arguments sent
to the remote library initialization.

Fixes #57
```

```
docs(contributing): add development setup instructions
```

#### Guidelines

- **Subject line:** 50 characters or less, imperative mood ("add" not "added").
- **Body:** wrap at 72 characters; explain what and why (not how).
- **Footer:** reference issues and breaking changes.
- **Breaking changes:** start the footer with "BREAKING CHANGE:" followed by a description.

#### Signed Commits Required

**All commits in a pull request must be cryptographically signed** to be accepted into the project. This helps ensure the authenticity and integrity of the codebase.

This refers to the **cryptographic commit signature** (`git commit -S`, GPG/SSH/X.509) — not to be confused with the DCO `Signed-off-by` trailer (`git commit -s`) mentioned in the [Legal Notice](#i-want-to-contribute).

**Setting up commit signing:**
- Follow GitHub's guide: [Managing commit signature verification](https://docs.github.com/en/authentication/managing-commit-signature-verification).
- Configure Git to sign commits automatically: `git config --global commit.gpgsign true`.
- Verify your commits are signed: `git log --show-signature`.

**For pull requests:**
- All commits in the PR must be signed.
- You can sign previous commits using: `git rebase --exec 'git commit --amend --no-edit -S' -i HEAD~<number-of-commits>`.
