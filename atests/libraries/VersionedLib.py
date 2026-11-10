"""Test-only library, loaded on the server via --pythonpath: a dynamic library that offers `Removed Later`
only if the server's variable LIB_VERSION is `before`, as a server update could remove a keyword."""

from typing import Any

from robot.libraries.BuiltIn import BuiltIn


class VersionedLib:
    def get_keyword_names(self) -> list[str]:
        version = BuiltIn().get_variable_value("${LIB_VERSION}")
        return ["Stays", "Removed Later"] if version == "before" else ["Stays"]

    def run_keyword(self, name: str, args: list[Any], kwargs: dict[str, Any] | None = None) -> str:
        return name
