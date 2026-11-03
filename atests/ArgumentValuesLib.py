"""Test-only library, imported both locally and on the server, to compare what its keywords get."""

from typing import Any

from robot.api.deco import keyword
from robot.libraries.BuiltIn import register_run_keyword


class ArgumentValuesLib:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._init = (args, sorted(kwargs.items()))

    def init_values(self) -> str:
        """Returns the ``repr`` of what the library got when it was imported."""
        return repr(self._init)

    def echo(self, value: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr(value)

    def var_args(self, *values: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr(values)

    def var_kwargs(self, **values: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr(sorted(values.items()))

    def words_of_a_variant(self, *words: Any) -> str:
        """Returns the ``repr`` of what it got, unresolved, which is what ``Run Keywords`` looks through."""
        return repr(words)

    @keyword("Embedded ${value} In The Name")
    def embedded(self, value: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr(value)

    @keyword("Embedded ${number:\\d+} With A Type")
    def embedded_with_a_type(self, number: int) -> str:
        """Returns the ``repr`` of what it got."""
        return repr(number)

    @keyword("Embedded ${value} And Another")
    def embedded_and_another(self, value: Any, other: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr((value, other))

    @keyword("Overlapping ${first} And ${second}")
    def overlapping_with_a_second_value(self, first: Any, second: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr(("two values", first, second))

    @keyword("Overlapping ${first} And More")
    def overlapping_with_one_value(self, first: Any) -> str:
        """Fits a call better than ``Overlapping ${first} And ${second}``, which also fits it."""
        return repr(("one value", first))

    def normal_keyword_next_to_a_pattern(self) -> str:
        """Its name also fits the pattern of the next keyword."""
        return repr("normal keyword")

    @keyword("Normal ${what} Next To A Pattern")
    def embedded_next_to_a_normal_keyword(self, what: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr(("embedded keyword", what))


register_run_keyword("ArgumentValuesLib", "words_of_a_variant", 0, deprecation_warning=False)
