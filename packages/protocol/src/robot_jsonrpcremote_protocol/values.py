"""The value format of the Robot protocol: how keyword arguments and return values travel.

A value that JSON holds travels as plain JSON. A value of a supported kind, such as a dataclass, an enum or a
``datetime``, travels as typed JSON in the form of its type where its place declares that type; where its place
declares none, it travels as a pickle of the whole value if both sides read pickles, and otherwise as typed JSON
that names its type in the key ``__type__``. Client and server have the same classes installed, in the same
modules, so a class needs no description of its own: the name of its module and its qualified name are enough.
"""

import base64
import binascii
import dataclasses
import datetime
import decimal
import enum
import importlib
import math
import pathlib
import pickle
import types
import typing
import uuid
from collections import OrderedDict
from typing import Any, Final

__all__ = [
    "NOT_DECLARED",
    "PICKLED_KEY",
    "TYPE_KEY",
    "VALUE_KEY",
    "PickleNotAgreedError",
    "ValueCannotTravelError",
    "ValueDoesNotFitError",
    "ValueFormat",
    "agreed_pickle_protocol",
    "resolve_type_name",
    "type_name",
]

PICKLED_KEY: Final = "__pickled__"
TYPE_KEY: Final = "__type__"
VALUE_KEY: Final = "value"


class _NotDeclared:
    """The declared type of a place that declares none."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NOT_DECLARED"


NOT_DECLARED: Final = _NotDeclared()


class ValueCannotTravelError(TypeError):
    """A value that may not travel: it is neither plain JSON nor typed JSON, and no pickles are agreed."""

    def __init__(self, message: str, type_name: str) -> None:
        super().__init__(message)
        self.type_name = type_name


class PickleNotAgreedError(ValueCannotTravelError):
    """A pickle that arrived although no pickles are agreed; it is not unpickled."""

    def __init__(self) -> None:
        super().__init__("A pickle arrived, but no pickles are agreed.", "pickle")


class ValueDoesNotFitError(ValueError):
    """A typed value that does not fit its type, whose class cannot be imported, or that names no supported kind."""

    def __init__(self, type_name: str, value: Any, reason: str) -> None:
        super().__init__(f"Value {value!r} cannot be converted to {type_name}: {reason}")
        self.type_name = type_name
        self.value = value
        self.reason = reason

    def describe(self, kind: str, name: str | None = None) -> str:
        """The failure as Robot Framework words a failed conversion, such as of the argument ``name`` of ``kind``."""
        typ = "" if isinstance(self.value, str) else f" ({_ROBOT_TYPE_NAMES.get(type(self.value), 'list')})"
        failure = f"cannot be converted to {self.type_name}: {self.reason}"
        if name is None:
            return f"{kind} '{self.value}'{typ} {failure}"
        return f"{kind} '{name}' got value '{self.value}'{typ} that {failure}"


# Robot Framework's names for the types of JSON values, as in its messages of failed conversions.
_ROBOT_TYPE_NAMES: Final[dict[type, str]] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "float",
    type(None): "None",
    dict: "dictionary",
    list: "list",
}


# The built-in and standard types that have a form of their own, by the names that Robot Framework gives them.
_NAMED_TYPES: Final[dict[str, type]] = {
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "dict": dict,
    "OrderedDict": OrderedDict,
    "float": float,
    "datetime": datetime.datetime,
    "date": datetime.date,
    "time": datetime.time,
    "timedelta": datetime.timedelta,
    "Decimal": decimal.Decimal,
    "bytes": bytes,
    "bytearray": bytearray,
    "UUID": uuid.UUID,
    "Path": pathlib.Path,
}
_NAMES_OF_TYPES: Final[dict[type, str]] = {cls: name for name, cls in _NAMED_TYPES.items()}

_NON_FINITE: Final = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}


def agreed_pickle_protocol(ours: int | None, theirs: int | None) -> int | None:
    """The pickle protocol that two sides agree on: the lower of the two, or ``None`` if one side reads none."""
    if ours is None or theirs is None:
        return None
    return min(ours, theirs)


def type_name(cls: type) -> str:
    """The name of ``cls`` in a library definition and in ``__type__``.

    The built-in and standard types of the protocol, and the other built-in types, go by the name that Robot
    Framework gives them; every other class by its module and its qualified name, such as ``mytypes.Point``.
    """
    name = _NAMES_OF_TYPES.get(cls)
    if name is not None:
        return name
    if issubclass(cls, pathlib.Path):
        # The concrete classes of the platform, PosixPath and WindowsPath.
        return "Path"
    if cls.__module__ == "builtins":
        return cls.__qualname__
    return f"{cls.__module__}.{cls.__qualname__}"


def resolve_type_name(name: str) -> Any:
    """The type that ``name`` names, as ``type_name`` writes it; raises ``LookupError`` if there is none.

    A dotted name is split from the right until a prefix imports as a module, and the rest is looked up as
    attributes, so ``mytypes.Outer.Inner`` tries ``mytypes.Outer`` and then ``mytypes``.
    """
    named = _NAMED_TYPES.get(name)
    if named is not None:
        return named
    parts = name.split(".")
    if len(parts) < 2:
        raise LookupError(f"there is no type {name!r}")
    failure: ImportError | None = None
    for split in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:split])
        try:
            found: Any = importlib.import_module(module_name)
        except ImportError as error:
            # The longest prefix that is no module gives the most precise message.
            failure = failure or error
            continue
        for attribute in parts[split:]:
            try:
                found = getattr(found, attribute)
            except AttributeError:
                raise LookupError(f"{module_name!r} has no attribute {attribute!r}") from None
        return found
    raise LookupError(str(failure))


def _is_dataclass_type(cls: Any) -> bool:
    return isinstance(cls, type) and dataclasses.is_dataclass(cls)


def _is_named_tuple_type(cls: Any) -> bool:
    return isinstance(cls, type) and issubclass(cls, tuple) and hasattr(cls, "_fields")


def _is_enum_type(cls: Any) -> bool:
    return isinstance(cls, type) and issubclass(cls, enum.Enum)


def _is_built_from_typed_json(cls: Any) -> bool:
    """Whether typed JSON builds values of ``cls``: the kinds that have a form."""
    return _is_dataclass_type(cls) or _is_named_tuple_type(cls) or _is_enum_type(cls) or cls in _NAMES_OF_TYPES


_HINTS: Final[dict[Any, dict[str, Any]]] = {}


def _hints(cls: Any) -> dict[str, Any]:
    """The type hints of the fields of ``cls``, kept once resolved; none if they cannot be resolved."""
    hints = _HINTS.get(cls)
    if hints is None:
        try:
            hints = typing.get_type_hints(cls)
        except Exception:
            hints = {}
        _HINTS[cls] = hints
    return hints


def _fixed(hint: Any) -> Any:
    """The type that ``hint`` fixes, or ``NOT_DECLARED``: a union fixes only its one member other than ``None``."""
    if hint is NOT_DECLARED or hint is Any:
        return NOT_DECLARED
    if typing.get_origin(hint) in (typing.Union, types.UnionType):
        members = [member for member in typing.get_args(hint) if member is not type(None)]
        return _fixed(members[0]) if len(members) == 1 else NOT_DECLARED
    return hint


def _class_and_arguments(hint: Any) -> tuple[Any, tuple[Any, ...]]:
    origin = typing.get_origin(hint)
    return (origin if origin is not None else hint), typing.get_args(hint)


def _item_hint(fixed: Any, container: type) -> Any:
    """The declared type of the items of a list or of the values of a dict, if ``fixed`` declares one."""
    cls, arguments = _class_and_arguments(fixed)
    if not isinstance(cls, type) or not issubclass(container, cls) or not arguments:
        return NOT_DECLARED
    if container is dict:
        return arguments[1] if len(arguments) == 2 else NOT_DECLARED
    return arguments[0]


def _has_marker(value: dict[Any, Any]) -> bool:
    return PICKLED_KEY in value or TYPE_KEY in value


class _NeedsPickleError(Exception):
    """A part of a value needs a pickle; the whole value is pickled then."""


# Returned by the declared paths when the declared type gives no form for the value.
_NO_FORM: Final = object()


@dataclasses.dataclass(frozen=True)
class ValueFormat:
    """The value format of one session: the agreed pickle protocol, or ``None``, and the further dict types.

    ``dict_types`` are types that travel as dicts, such as Robot Framework's ``DotDict``; they arrive as plain
    dicts. ``declared`` is the Python type hint of the place of a value, or ``NOT_DECLARED``.
    """

    pickle_protocol: int | None = None
    dict_types: tuple[type, ...] = ()

    @property
    def pickles(self) -> bool:
        return self.pickle_protocol is not None

    def encode(self, value: Any, declared: Any = NOT_DECLARED) -> Any:
        try:
            return self._encode(value, declared)
        except _NeedsPickleError:
            # A pickle is only ever a whole value, since it is only unpacked at the top level.
            return {PICKLED_KEY: pickle.dumps(value, protocol=self.pickle_protocol).hex()}

    def decode(self, data: Any, declared: Any = NOT_DECLARED) -> Any:
        if type(data) is dict and PICKLED_KEY in data:
            if not self.pickles:
                raise PickleNotAgreedError
            return pickle.loads(bytes.fromhex(data[PICKLED_KEY]))
        return self._decode(data, declared)

    # --- encoding ---------------------------------------------------------------------------------------------

    def _is_dict(self, value: Any) -> bool:
        return type(value) is dict or type(value) in self.dict_types

    def _encode(self, value: Any, declared: Any) -> Any:
        kind = type(value)
        if value is None or kind is str or kind is bool or kind is int or (kind is float and math.isfinite(value)):
            return value
        fixed = _fixed(declared)
        if kind is list:
            return [self._encode(item, _item_hint(fixed, list)) for item in value]
        if self._is_dict(value) and all(type(key) is str for key in value) and not _has_marker(value):
            return {key: self._encode(item, _item_hint(fixed, dict)) for key, item in value.items()}
        if fixed is not NOT_DECLARED:
            form = self._declared_form(value, fixed)
            if form is not _NO_FORM:
                return form
        if self.pickles:
            raise _NeedsPickleError
        return self._tagged(value)

    def _declared_form(self, value: Any, fixed: Any) -> Any:
        """The form of ``value`` for the declared type ``fixed``, or ``_NO_FORM`` if it is not of that type."""
        cls, arguments = _class_and_arguments(fixed)
        if not isinstance(cls, type):
            return _NO_FORM
        kind = type(value)
        if cls is pathlib.Path:
            return value.as_posix() if isinstance(value, pathlib.Path) else _NO_FORM
        if cls is dict and self._is_dict(value):
            kind = dict
        if kind is not cls:
            return _NO_FORM
        if _is_dataclass_type(cls):
            field_hints = _hints(cls)
            return {
                field.name: self._encode(getattr(value, field.name), field_hints.get(field.name, NOT_DECLARED))
                for field in dataclasses.fields(value)
            }
        if _is_named_tuple_type(cls):
            field_hints = _hints(cls)
            return [self._encode(item, field_hints.get(name, NOT_DECLARED)) for name, item in zip(value._fields, value)]
        if _is_enum_type(cls):
            return value.name
        if cls is float:
            return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        if cls is tuple:
            if len(arguments) == 2 and arguments[1] is Ellipsis:
                item_hints: list[Any] = [arguments[0]] * len(value)
            elif arguments and arguments != ((),):
                item_hints = list(arguments)
            else:
                item_hints = [NOT_DECLARED] * len(value)
            return [self._encode(item, hint) for item, hint in zip(value, item_hints, strict=False)]
        if cls is set or cls is frozenset:
            item = arguments[0] if arguments else NOT_DECLARED
            return [self._encode(member, item) for member in value]
        if cls is dict or cls is OrderedDict:
            key_hint, value_hint = arguments if len(arguments) == 2 else (NOT_DECLARED, NOT_DECLARED)
            if all(type(key) is str for key in value):
                if _has_marker(value):
                    return _NO_FORM
                return {key: self._encode(item, value_hint) for key, item in value.items()}
            return [[self._encode(key, key_hint), self._encode(item, value_hint)] for key, item in value.items()]
        if cls in (datetime.datetime, datetime.date, datetime.time):
            return value.isoformat()
        if cls is datetime.timedelta:
            return value.total_seconds()
        if cls is decimal.Decimal or cls is uuid.UUID:
            return str(value)
        if cls is bytes or cls is bytearray:
            return base64.b64encode(value).decode("ascii")
        return _NO_FORM

    def _tagged(self, value: Any) -> Any:
        """``value`` as typed JSON that names its type, where its place declares none and no pickles are agreed."""
        cls = pathlib.Path if isinstance(value, pathlib.Path) else type(value)
        if self._is_dict(value):
            cls = dict
        form = self._declared_form(value, cls) if _is_built_from_typed_json(cls) else _NO_FORM
        if form is _NO_FORM:
            name = type_name(type(value))
            raise ValueCannotTravelError(f"A value of type {name!r} is not JSON, and no pickles are agreed.", name)
        if _is_dataclass_type(cls):
            return {TYPE_KEY: type_name(cls), **typing.cast(dict[str, Any], form)}
        return {TYPE_KEY: type_name(cls), VALUE_KEY: form}

    # --- decoding ---------------------------------------------------------------------------------------------

    def _decode(self, data: Any, declared: Any) -> Any:
        if data is None:
            return None
        if type(data) is dict:
            if TYPE_KEY in data:
                return self._decode_tagged(data)
            if PICKLED_KEY in data:
                raise ValueDoesNotFitError("pickle", data, "a pickle only travels as a whole value")
        fixed = _fixed(declared)
        if fixed is not NOT_DECLARED:
            built = self._decode_declared(data, fixed)
            if built is not _NO_FORM:
                return built
        if type(data) is list:
            return [self._decode(item, NOT_DECLARED) for item in data]
        if type(data) is dict:
            return {key: self._decode(item, NOT_DECLARED) for key, item in data.items()}
        return data

    def _decode_tagged(self, data: dict[str, Any]) -> Any:
        name = data[TYPE_KEY]
        if type(name) is not str:
            raise ValueDoesNotFitError(repr(name), data, "the name of a type is a text")
        try:
            cls = resolve_type_name(name)
        except LookupError as error:
            raise ValueDoesNotFitError(name, data, f"it cannot be imported: {error}") from None
        if not _is_built_from_typed_json(cls):
            raise ValueDoesNotFitError(
                name, data, "typed JSON builds only dataclasses, enums, named tuples and the types of the protocol"
            )
        if _is_dataclass_type(cls):
            return self._decode_dataclass({key: item for key, item in data.items() if key != TYPE_KEY}, cls)
        if VALUE_KEY not in data:
            raise ValueDoesNotFitError(name, data, f"its form is missing in the key {VALUE_KEY!r}")
        built = self._decode_declared(data[VALUE_KEY], cls)
        return data[VALUE_KEY] if built is _NO_FORM else built

    def _decode_declared(self, data: Any, fixed: Any) -> Any:
        """The value of ``data`` for the declared type ``fixed``, or ``_NO_FORM`` if that type builds nothing."""
        cls, arguments = _class_and_arguments(fixed)
        if not isinstance(cls, type):
            return _NO_FORM
        name = type_name(cls)

        def does_not_fit(reason: str) -> ValueDoesNotFitError:
            return ValueDoesNotFitError(name, data, reason)

        if cls is list or cls is dict:
            # Plain JSON kinds: a form that is no list or dict stays as it is.
            return self._decode_container(data, cls, arguments)
        if cls is float:
            return _NON_FINITE[data] if type(data) is str and data in _NON_FINITE else _NO_FORM
        if not _is_built_from_typed_json(cls):
            return _NO_FORM
        if _is_dataclass_type(cls):
            if type(data) is not dict:
                raise does_not_fit("its form is an object with its fields")
            return self._decode_dataclass(data, cls)
        if _is_named_tuple_type(cls):
            named_tuple: Any = cls
            fields: tuple[str, ...] = named_tuple._fields
            if type(data) is not list or len(data) != len(fields):
                raise does_not_fit(f"its form is an array of {len(fields)} items")
            field_hints = _hints(cls)
            items = (self._decode(item, field_hints.get(field, NOT_DECLARED)) for field, item in zip(fields, data))
            return named_tuple(*items)
        if _is_enum_type(cls):
            if type(data) is not str:
                raise does_not_fit("its form is the name of a member")
            try:
                return typing.cast(type[enum.Enum], cls)[data]
            except KeyError:
                raise does_not_fit(f"{name} has no member {data!r}") from None
        if cls is tuple or cls is set or cls is frozenset:
            if type(data) is not list:
                raise does_not_fit("its form is an array")
            if cls is tuple and len(arguments) == 2 and arguments[1] is Ellipsis:
                hints_of_items: list[Any] = [arguments[0]] * len(data)
            elif cls is tuple and arguments and arguments != ((),):
                if len(arguments) != len(data):
                    raise does_not_fit(f"its form is an array of {len(arguments)} items")
                hints_of_items = list(arguments)
            else:
                hints_of_items = [arguments[0] if arguments else NOT_DECLARED] * len(data)
            return cls(self._decode(item, hint) for item, hint in zip(data, hints_of_items))
        if cls is OrderedDict:
            built = self._decode_container(data, dict, arguments)
            if built is _NO_FORM:
                raise does_not_fit("its form is an object or an array of pairs")
            return OrderedDict(built)
        if type(data) is not str and cls is not datetime.timedelta:
            raise does_not_fit("its form is a text")
        try:
            if cls is datetime.datetime:
                return datetime.datetime.fromisoformat(data)
            if cls is datetime.date:
                return datetime.date.fromisoformat(data)
            if cls is datetime.time:
                return datetime.time.fromisoformat(data)
            if cls is datetime.timedelta:
                if type(data) not in (int, float):
                    raise does_not_fit("its form is a number of seconds")
                return datetime.timedelta(seconds=typing.cast(float, data))
            if cls is decimal.Decimal:
                return decimal.Decimal(data)
            if cls is uuid.UUID:
                return uuid.UUID(data)
            if cls is bytes or cls is bytearray:
                return cls(base64.b64decode(data, validate=True))
            if cls is pathlib.Path:
                return pathlib.Path(data)
        except (ValueError, decimal.InvalidOperation, binascii.Error) as error:
            if isinstance(error, ValueDoesNotFitError):
                raise
            raise does_not_fit(str(error) or type(error).__name__) from None
        return _NO_FORM

    def _decode_container(self, data: Any, cls: type, arguments: tuple[Any, ...]) -> Any:
        if cls is list:
            if type(data) is not list:
                return _NO_FORM
            item = arguments[0] if arguments else NOT_DECLARED
            return [self._decode(member, item) for member in data]
        key_hint, value_hint = arguments if len(arguments) == 2 else (NOT_DECLARED, NOT_DECLARED)
        if type(data) is dict:
            return {key: self._decode(item, value_hint) for key, item in data.items()}
        if type(data) is list and all(type(pair) is list and len(pair) == 2 for pair in data):
            return {self._decode(key, key_hint): self._decode(item, value_hint) for key, item in data}
        return _NO_FORM

    def _decode_dataclass(self, data: dict[str, Any], cls: type) -> Any:
        name = type_name(cls)
        fields = dataclasses.fields(cls)
        known = {field.name for field in fields}
        for key in data:
            if key not in known:
                raise ValueDoesNotFitError(name, data, f"it has no field {key!r}")
        for field in fields:
            required = field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
            if field.init and required and field.name not in data:
                raise ValueDoesNotFitError(name, data, f"missing field {field.name!r}")
        hints = _hints(cls)
        arguments = {
            field.name: self._decode(data[field.name], hints.get(field.name, NOT_DECLARED))
            for field in fields
            if field.init and field.name in data
        }
        try:
            return cls(**arguments)
        except (TypeError, ValueError) as error:
            raise ValueDoesNotFitError(name, data, str(error)) from None
