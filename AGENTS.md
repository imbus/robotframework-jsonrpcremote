# Repository Guidelines

This file is a short orientation layer for automated contributors. For complete contributor details, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Quick Orientation

robotframework-jsonrpcremote is a [uv](https://github.com/astral-sh/uv) workspace (monorepo) implementing a Robot Framework remote library over JSON-RPC 2.0.

- Client library (the importable `JsonRpcRemote`): `src/JsonRpcRemote/`
- Protocol definitions: `packages/protocol/src/robot_jsonrpcremote_protocol/`
- JSON-RPC peer (asyncio): `packages/jsonrpcpeer/src/jsonrpcpeer/`
- Server runtime (`robot-jsonrpcremote-server` CLI): `packages/server/src/robot_jsonrpcremote_server/`
- Examples: `examples/simple-robot-jsonrpcserver/`
- Unit tests (pytest): `tests/unit/`
- Robot Framework integration tests: `tests/robot/`

## Task Routing

- Client library:
	- Owning path: `src/JsonRpcRemote/`.
- Server runtime:
	- Owning path: `packages/server/src/robot_jsonrpcremote_server/`.
- JSON-RPC peer:
	- Owning path: `packages/jsonrpcpeer/src/jsonrpcpeer/`.
- Protocol:
	- Owning path: `packages/protocol/src/robot_jsonrpcremote_protocol/`. It is the source of truth shared by client and server — keep both sides compatible when changing it.
- Examples:
	- Owning path: `examples/`.
- Tests:
	- Unit tests live in `tests/unit/` (pytest), organized by component (`test_peer.py`, `test_endpoint.py`, `test_protocol.py`, ...). Add or update them for any Python change.
	- End-to-end behavior is covered by Robot Framework suites in `tests/robot/`; each suite starts and stops its own server.
- Generated or ignored outputs (do not commit by hand):
	- Build artifacts in `dist/`, Robot output in `results/`, and the various caches are gitignored.

## Common Commands

All commands run inside the project environment via `uv run` (or after activating `.venv`).

- `uv sync --all-extras --all-packages --dev`
	- One-time setup: create `.venv` and install the client, all workspace packages, and the dev tools.
- `uv run --all-packages pytest`
	- Unit tests (collected from `tests/unit`). Run on every change. `--all-packages` is required: `uv run` targets the workspace root and re-syncs exactly, so the server package would otherwise be pruned (`ModuleNotFoundError`).
- `uv run --all-packages robotcode run`
	- Robot Framework integration tests under `tests/robot/`. Output is written to `results/` by default.
- `uv run ruff check .`
	- Lint.
- `uv run ruff format .` / `uv run ruff format --check .`
	- Apply / verify formatting.
- `uv run mypy src packages/*/src examples/*/src tests/unit`
	- Type checking (strict). mypy has no default target, so pass the source directories explicitly. This is the authoritative type-check gate.
- `uv run robocop check` / `uv run robocop format`
	- Lint / format the `.robot` files in `tests/robot/` (optional).
- `uv build --all-packages`
	- Build wheels and sdists for all packages into `dist/`.

## Commits and Pull Requests

These rules are required by the contribution guide; follow them for every change.

- **Conventional Commits** are required (`type(scope): subject`). Allowed types and scopes are listed in [CONTRIBUTING.md § Commit Messages](CONTRIBUTING.md#commit-messages) — scopes are `client`, `server`, `peer`, `protocol`, `examples`, `tests`, `docs`, `build`.
- **Cryptographically signed commits** are mandatory (`git commit -S`, GPG/SSH). This is separate from the DCO `Signed-off-by` trailer (`-s`).
- **AI / tooling disclosure** is required when an AI agent contributed substantially. See [AI_POLICY.md](AI_POLICY.md).
- Keep changes focused. No unrelated refactors or formatting noise in the same PR.

## Agent Notes

- Make small, focused changes and avoid unrelated refactors.
- Before opening a PR, make sure `uv run pytest`, `uv run ruff check .`, and `uv run mypy ...` pass; run `uv run robotcode run` for changes that affect client/server behavior.
- Update [CONTRIBUTING.md](CONTRIBUTING.md) when contributor rules change; update this file when the orientation, task routing, or common commands change.
