"""Runs Libdoc in a process of its own and reads its spec files, like a tool that works with them."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


def _write_spec(library: str, spec_format: str, output: str) -> None:
    command = [sys.executable, "-m", "robot.libdoc", "--format", spec_format, library, output]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise AssertionError(
            f"Libdoc failed with exit code {completed.returncode}:\n{completed.stdout}{completed.stderr}"
        )


class LibdocSpecs:
    def keywords_in_json_spec(self, library: str, output: str) -> dict[str, dict[str, Any]]:
        """Writes the JSON spec file of ``library`` to ``output`` and returns its keywords by name."""
        _write_spec(library, "JSON", output)
        return {
            keyword["name"]: keyword for keyword in json.loads(Path(output).read_text(encoding="utf-8"))["keywords"]
        }

    def keywords_in_xml_spec(self, library: str, output: str) -> dict[str, dict[str, str]]:
        """Writes the XML spec file of ``library`` to ``output`` and returns the attributes of its keywords by name."""
        _write_spec(library, "XML", output)
        return {keyword.attrib["name"]: dict(keyword.attrib) for keyword in ElementTree.parse(output).iter("kw")}
