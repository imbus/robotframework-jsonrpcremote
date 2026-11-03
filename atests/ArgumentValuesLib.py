"""Test-only library, imported both locally and on the server, to compare what its keywords get."""

from typing import Any

from robot.api.deco import keyword
from robot.libraries.BuiltIn import register_run_keyword


class Thing:
    """An object that only Python peers can exchange, and only with this module on both sides."""

    def __init__(self, value: Any) -> None:
        self.value = value


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

    def positional_only(self, first: Any, second: Any = 2, /) -> str:
        """Returns the ``repr`` of what it got."""
        return repr((first, second))

    def named_only(self, first: Any, *, key: Any, other: Any = "o") -> str:
        """Returns the ``repr`` of what it got."""
        return repr((first, key, other))

    def all_kinds(self, first: Any, /, second: Any = 2, *rest: Any, key: Any = "k", **others: Any) -> str:
        """Returns the ``repr`` of what it got."""
        return repr((first, second, rest, key, sorted(others.items())))

    def same_value(self, value: Any) -> Any:
        """Returns the value that it got."""
        return value

    def type_name_of(self, value: Any) -> str:
        """Returns the name of the type of the value that it got."""
        return type(value).__name__

    def make_thing(self, value: Any) -> Thing:
        """Returns an instance of a class of this library."""
        return Thing(value)

    def value_of_thing(self, thing: Thing) -> Any:
        """Returns the value of an instance of a class of this library."""
        return thing.value

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
