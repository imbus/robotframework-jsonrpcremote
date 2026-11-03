"""Test-only library, for Libdoc locally and on the server: its keywords must look the same in both specs.

It has no return annotations and no types of its own: a remote library reports neither to Libdoc.
"""

from datetime import date
from typing import Any, Literal, Optional

from robot.api.deco import keyword


class LibdocLib:
    """Documentation of the library."""

    def plain(self):
        pass

    def documented(self, value):
        """First line of the documentation.

        More of it, with *bold* text.
        """

    @keyword(tags=["tag one", "tag two"])
    def tagged(self):
        """Documentation of a keyword with tags.

        Tags: tag three
        """

    def all_kinds(
        self,
        first: str,
        /,
        second: int = 5,
        *rest: str,
        named: bool = True,
        plain=None,
        nested=[1, {"a": 2}],
        **others: int,
    ):
        """Every kind of argument."""

    def many_types(
        self,
        a: int | None,
        b: "list[int]",
        c: dict[str, int],
        d: date | None = None,
        e: Literal["x", "y"] = "x",
        f: Optional[float] = None,
        g: Any = 1,
        h: bytes = b"ab",
    ):
        """Many types."""

    @keyword("Embedded ${value} In The Name")
    def embedded(self, value, other="x"):
        """Embedded argument and another one."""

    @keyword("Embedded ${number:\\d+} With A Type")
    def embedded_with_a_type(self, number: int):
        pass
