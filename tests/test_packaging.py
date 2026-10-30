"""Each package declares the distributions of the packages that its modules import."""

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

# The distribution that provides each top-level module that the packages import from outside the
# standard library.
DISTRIBUTIONS = {
    "jsonrpcpeer": "jsonrpcpeer",
    "robot": "robotframework",
    "robot_jsonrpcremote_protocol": "robotframework-jsonrpcremote-protocol",
    "typing_extensions": "typing-extensions",
}


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _imported_modules(package: Path) -> set[str]:
    modules: set[str] = set()
    for source in package.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return {module for module in modules if module not in sys.stdlib_module_names and module != package.name}


def _declared_distributions(pyproject: Path) -> set[str]:
    dependencies = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"].get("dependencies", [])
    return {_normalize(re.split(r"[\s;<>=!~\[]", dependency, maxsplit=1)[0]) for dependency in dependencies}


@pytest.mark.parametrize(
    ("package", "pyproject"),
    [
        ("src/JsonRpcRemote", "pyproject.toml"),
        ("packages/server/src/robot_jsonrpcremote_server", "packages/server/pyproject.toml"),
        ("packages/protocol/src/robot_jsonrpcremote_protocol", "packages/protocol/pyproject.toml"),
        ("packages/jsonrpcpeer/src/jsonrpcpeer", "packages/jsonrpcpeer/pyproject.toml"),
    ],
)
def test_a_package_declares_every_distribution_it_imports(package: str, pyproject: str) -> None:
    imported = _imported_modules(ROOT / package)
    declared = _declared_distributions(ROOT / pyproject)
    assert {_normalize(DISTRIBUTIONS.get(module, module)) for module in imported} <= declared
