import collections.abc
import dataclasses
import enum
import functools
import inspect
import itertools
import json
import pickle
import re
import types
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from typing_extensions import TypeForm

__all__ = [
    "CamelSnakeMixin",
    "ValidateMixin",
    "as_dict",
    "as_json",
    "from_dict",
    "from_json",
    "to_camel_case",
    "to_snake_case",
]

_RE_SNAKE_CASE_1 = re.compile(r"[\-\.\s]")
_RE_SNAKE_CASE_2 = re.compile(r"[A-Z]")


__NOT_SET = object()


@functools.lru_cache(maxsize=1024)
def to_snake_case(s: str) -> str:
    s = _RE_SNAKE_CASE_1.sub("_", s)
    if not s:
        return s
    return s[0].lower() + _RE_SNAKE_CASE_2.sub(lambda matched: "_" + matched.group(0).lower(), s[1:])


_RE_CAMEL_CASE_1 = re.compile(r"^[\-_\.]")
_RE_CAMEL_CASE_2 = re.compile(r"[\-_\.\s]([a-z])")


@functools.lru_cache(maxsize=1024)
def to_camel_case(s: str) -> str:
    s = _RE_CAMEL_CASE_1.sub("", s)
    if not s:
        return s
    return str(s[0]).lower() + _RE_CAMEL_CASE_2.sub(lambda matched: str(matched.group(1)).upper(), s[1:])


class CamelSnakeMixin:
    @classmethod
    def _encode_case(cls, s: str) -> str:
        return to_camel_case(s)

    @classmethod
    def _decode_case(cls, s: str) -> str:
        return to_snake_case(s)


_T = TypeVar("_T")


@functools.lru_cache(maxsize=1024)
def _encode_case_for_field_name_cached(t: Type[Any], field: dataclasses.Field[Any]) -> str:
    alias = field.metadata.get("alias", None)
    if alias:
        return str(alias)

    if hasattr(t, "_encode_case"):
        return str(t._encode_case(field.name))

    return field.name


def encode_case_for_field_name(obj: Any, field: dataclasses.Field) -> str:  # type: ignore
    t = obj if isinstance(obj, type) else type(obj)
    return _encode_case_for_field_name_cached(t, field)


@functools.lru_cache(maxsize=1024)
def _decode_case_for_member_name(type: Type[Any], name: str) -> str:
    if dataclasses.is_dataclass(type):
        field = next(
            (f for f in get_dataclass_fields(type) if f.metadata.get("alias", None) == name),
            None,
        )
        if field:
            return field.name

    if hasattr(type, "_decode_case"):
        return str(type._decode_case(name))

    return name


NONETYPE = type(None)

__dataclasses_cache: Dict[Type[Any], Tuple[dataclasses.Field, ...]] = {}  # type: ignore
__handlers_cache: Dict[Type[Any], Callable[[Any, bool, bool], Any]] = {}


def get_dataclass_fields(t: Type[Any]) -> Tuple[dataclasses.Field, ...]:  # type: ignore
    fields = __dataclasses_cache.get(t)
    if fields is None:
        fields = __dataclasses_cache[t] = dataclasses.fields(t)
        return fields
    return fields


def _default(o: Any) -> Any:
    if dataclasses.is_dataclass(o):
        return {
            name: value
            for name, value, field in (
                (
                    encode_case_for_field_name(o, field),
                    getattr(o, field.name),
                    field,
                )
                for field in get_dataclass_fields(type(o))
                if (field.init or field.metadata.get("force_json", False)) and not field.metadata.get("nosave", False)
            )
            if value is not None or field.default == dataclasses.MISSING
        }
    if isinstance(o, enum.Enum):
        return o.value
    if isinstance(o, (set, frozenset)):
        return list(o)

    raise TypeError(f"Can't get default value for {type(o)} with value {o!r}")


def as_json(obj: Any, indent: Optional[bool] = None, compact: Optional[bool] = None) -> str:
    return json.dumps(
        obj,
        default=_default,
        indent=4 if indent else None,
        separators=(",", ":") if compact else None,
        ensure_ascii=False,
    )


class NamedTypeError(TypeError):
    def __init__(self, name: str, message: str) -> None:
        super().__init__(f'Invalid value for "{name}": {message}')
        self.name = name
        self.message = message


__get_args_cache: Dict[Type[Any], Tuple[Any, ...]] = {}


def _get_args_cached(t: Type[Any]) -> Tuple[Any, ...]:
    r = __get_args_cache.get(t, __NOT_SET)
    if r is __NOT_SET:
        r = get_args(t)
        __get_args_cache[t] = r
    return cast(Tuple[Any, ...], r)


__get_origin_cache: Dict[Type[Any], Optional[Any]] = {}


def _get_origin_cached(t: Type[Any]) -> Optional[Any]:
    r = __get_origin_cache.get(t, __NOT_SET)
    if r is __NOT_SET:
        r = __get_origin_cache[t] = get_origin(t)
    return r


__get_type_hints_cache: Dict[Type[Any], Dict[str, Any]] = {}


def _get_type_hints_cached(t: Type[Any]) -> Dict[str, Any]:
    r = __get_type_hints_cache.get(t, __NOT_SET)
    if r is __NOT_SET:
        r = __get_type_hints_cache[t] = get_type_hints(t)
    return cast(Dict[str, Any], r)


__signature_cache: Dict[Type[Any], inspect.Signature] = {}


def _get_signature_cached(t: Type[Any]) -> inspect.Signature:
    r = __signature_cache.get(t, __NOT_SET)
    if r is __NOT_SET:
        r = __signature_cache[t] = inspect.signature(t)
    return cast(inspect.Signature, r)


def _from_dict_with_name(
    name: str,
    value: Any,
    types: Any = None,
    /,
    *,
    strict: bool = False,
) -> Any:
    try:
        return from_dict(value, types, strict=strict)
    except NamedTypeError as e:
        raise NamedTypeError(name + "." + e.name, e.message) from e
    except TypeError as e:
        raise NamedTypeError(name, str(e)) from e


__is_class_cache: Dict[Type[Any], bool] = {}


def is_class_cached(t: Type[Any]) -> bool:
    r = __is_class_cache.get(t, __NOT_SET)
    if r is __NOT_SET:
        r = __is_class_cache[t] = inspect.isclass(t)
    return cast(bool, r)


__is_subclass_cache: Dict[Tuple[Type[Any], Type[Any]], bool] = {}


def is_subclass_cached(t: Type[Any], base: Type[Any]) -> bool:
    r = __is_subclass_cache.get((t, base), __NOT_SET)
    if r is __NOT_SET:
        r = inspect.isclass(t) and issubclass(t, base)
        __is_subclass_cache[(t, base)] = r
    return cast(bool, r)


def __from_dict_handle_union(value: Any, t: Type[Any], strict: bool) -> Tuple[Any, bool]:
    return from_dict(value, _get_args_cached(t), strict=strict), True


def __from_dict_handle_literal(value: Any, t: Type[Any], strict: bool) -> Tuple[Any, bool]:
    args = _get_args_cached(t)
    if value in args:
        return value, True

    return None, False


def __is_enum(t: Type[Any]) -> bool:
    origin = _get_origin_cached(t)
    return is_class_cached(origin or t) and is_subclass_cached(origin or t, enum.Enum)


def __from_dict_handle_enum(value: Any, t: Type[Any], strict: bool) -> Tuple[Any, bool]:
    for v in cast(Iterable[Any], t):
        if v.value == value:
            return v, True
    return None, False


def __from_dict_handle_basic_types(value: Any, t: Type[Any], strict: bool) -> Tuple[Any, bool]:
    # A JSON boolean is no number, although `bool` is a subclass of `int`.
    if isinstance(value, bool):
        return (value, True) if t is bool else (None, False)

    if isinstance(value, t):
        return value, True

    if not strict:
        if t is float and isinstance(value, int):
            return float(value), True

    return None, False


__ABSTRACT_LIST_TYPES = {
    collections.abc.Sequence,
    collections.abc.MutableSequence,
    collections.abc.Collection,
    collections.abc.Iterable,
}


def __from_dict_handle_sequence(value: Any, t: Type[Any], strict: bool) -> Tuple[Any, bool]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        args = _get_args_cached(t)
        origin = _get_origin_cached(t) or t
        target = list if origin in __ABSTRACT_LIST_TYPES else origin
        return target(from_dict(v, args, strict=strict) for v in value), True
    return None, False


def __from_dict_handle_tuple(value: Any, t: Type[Any], strict: bool) -> Tuple[Any, bool]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return None, False

    origin = _get_origin_cached(t) or t
    args = _get_args_cached(t)

    if hasattr(origin, "_fields"):
        if len(value) > len(origin._fields):
            return None, False

        hints = _get_type_hints_cached(origin)
        items = [from_dict(v, hints.get(n), strict=strict) for n, v in zip(origin._fields, value)]
        try:
            return origin(*items), True
        except TypeError:
            return None, False

    if not args:
        return origin(value), True

    if len(args) == 2 and args[1] is Ellipsis:
        return tuple(from_dict(v, args[0], strict=strict) for v in value), True

    if len(args) != len(value):
        return None, False

    return tuple(from_dict(v, a, strict=strict) for v, a in zip(value, args)), True


def __from_dict_handle_mapping(value: Any, t: Type[Any], strict: bool) -> Tuple[Any, bool]:
    if isinstance(value, Mapping):
        args = _get_args_cached(t)
        key_type = args[0] if args else None
        value_type = args[1] if len(args) > 1 else None
        return {
            _from_dict_with_name(str(n), n, key_type, strict=strict): _from_dict_with_name(
                str(n), v, value_type, strict=strict
            )
            for n, v in value.items()
        }, True
    return None, False


def is_union(tp: Optional[Type[Any]]) -> bool:
    return tp is Union or tp is types.UnionType  # type: ignore[comparison-overlap]


__from_dict_handlers: List[
    Tuple[
        Callable[[Type[Any]], bool],
        Callable[[Any, Type[Any], bool], Tuple[Any, bool]],
    ]
] = [
    (
        lambda t: t in {int, bool, float, str, NONETYPE},
        __from_dict_handle_basic_types,
    ),
    (lambda t: is_union(_get_origin_cached(t)), __from_dict_handle_union),
    (lambda t: _get_origin_cached(t) is Literal, __from_dict_handle_literal),
    (__is_enum, __from_dict_handle_enum),
    (lambda t: is_subclass_cached(_get_origin_cached(t) or t, tuple), __from_dict_handle_tuple),
    (
        lambda t: (
            (_get_origin_cached(t) or t) in __ABSTRACT_LIST_TYPES
            or is_subclass_cached(_get_origin_cached(t) or t, Sequence)
        ),
        __from_dict_handle_sequence,
    ),
    (
        lambda t: is_subclass_cached(_get_origin_cached(t) or t, Mapping),
        __from_dict_handle_mapping,
    ),
    (lambda t: t is Any, lambda v, _t, _: (v, True)),
]

__from_dict_handlers_cache: Dict[Type[Any], Optional[Callable[[Any, Type[Any], bool], Tuple[Any, bool]]]] = {}

__non_default_parameters_cache: Dict[Type[Any], Set[str]] = {}


def __get_non_default_parameter(t: Type[Any], signature: inspect.Signature) -> Set[str]:
    r = __non_default_parameters_cache.get(t)
    if r is None:
        r = __non_default_parameters_cache[t] = {
            k for k, v in signature.parameters.items() if v.default == inspect.Parameter.empty
        }
    return r


__signature_keys_cache: Dict[Type[Any], Set[str]] = {}


def __get_signature_keys_cached(t: Type[Any], signature: inspect.Signature) -> Set[str]:
    r = __signature_keys_cache.get(t)
    if r is None:
        r = __signature_keys_cache[t] = set(signature.parameters.keys())
    return r


def __from_dict_create(t: Type[Any], value: Dict[str, Any], type_hints: Dict[str, Any], strict: bool) -> Any:
    params: Dict[str, Any] = {
        k: _from_dict_with_name(k, v, type_hints[k], strict=strict) for k, v in value.items() if k in type_hints
    }

    try:
        return t(**params)
    except TypeError as ex:
        raise TypeError(f"Can't initialize {t!r} with parameters {params!r}: {ex}") from ex


@overload
def from_dict(value: Any, types: None = ..., /, *, strict: bool = ...) -> Any: ...


@overload
def from_dict(value: Any, types: tuple[type[_T], ...], /, *, strict: bool = ...) -> _T: ...


@overload
def from_dict(value: Any, types: TypeForm[_T], /, *, strict: bool = ...) -> _T: ...


def from_dict(
    value: Any,
    types: Any = None,
    /,
    *,
    strict: bool = False,
) -> Any:
    # NOTE: `types` is typed as `Any` here on purpose. The overloads above give
    # callers precise inference for plain classes and tuples of classes, while
    # still accepting typing special forms (Optional[int], Literal[...], list[int],
    # unions, ...) which are not `type[...]` and would otherwise be rejected.
    if types is None:
        return value

    if not isinstance(types, tuple):
        types = (types,)
    if not types:
        return value

    first_error: Optional[TypeError] = None
    mapping_result: Any = __NOT_SET

    for t in types:
        func = __from_dict_handlers_cache.get(t, __NOT_SET)
        if func is __NOT_SET:
            func = None
            for h in __from_dict_handlers:
                if h[0](t):
                    func = h[1]
                    break

            __from_dict_handlers_cache[t] = func

        if func is None:
            continue

        # An element that does not fit one type of a union says nothing about its other types.
        try:
            r, ok = func(value, t, strict)  # type: ignore[operator]
        except TypeError as e:
            first_error = first_error or e
            continue

        if ok:
            if func is not __from_dict_handle_mapping or len(types) == 1:
                return r

            mapping_result = r
            break

    if isinstance(value, Mapping):
        matches: List[Tuple[Type[Any], Dict[str, Any], Dict[str, Any]]] = []
        match_same_keys = -1
        # A dict type keeps every key, so next to one, a class has to know them all.
        known_keys_only = strict or mapping_result is not __NOT_SET

        for t in types:
            if t is type(None):
                continue

            origin = _get_origin_cached(t)

            # A union got here because none of its types fit, and it is no class to fill.
            if origin is Literal or is_union(origin):
                continue

            # Without declared fields, a class has nothing to fill from the keys of an object.
            type_hints = _get_type_hints_cached(origin or t)
            if not type_hints and not dataclasses.is_dataclass(origin or t):
                continue

            cased_value: Dict[str, Any] = {_decode_case_for_member_name(t, k): v for k, v in value.items()}

            try:
                signature = _get_signature_cached(origin or t)
            except ValueError:
                continue

            non_default_parameters = __get_non_default_parameter(origin or t, signature)

            if len(value) == 0 and non_default_parameters:
                continue

            sig_keys = __get_signature_keys_cached(origin or t, signature)

            same_keys = cased_value.keys() & sig_keys

            if known_keys_only and any(k not in sig_keys for k in cased_value):
                continue

            if not all(k in same_keys for k in non_default_parameters):
                continue

            if len(same_keys) > match_same_keys:
                match_same_keys = len(same_keys)
                matches = []

            if len(same_keys) == match_same_keys:
                matches.append((t, cased_value, type_hints))

        # The keys decide first. Among classes with equally many of them, the values decide.
        created: List[Any] = []
        for match, match_value, match_type_hints in matches:
            try:
                created.append(__from_dict_create(match, match_value, match_type_hints, strict))
            except TypeError as e:
                first_error = first_error or e

        if len(created) == 1:
            return created[0]

        if created and mapping_result is __NOT_SET:
            raise TypeError(
                f"Value {value!r} of type {type(value)!r} matches more than one of the types "
                f"{' | '.join(repr(type(e).__name__) for e in created)}."
            )

    if mapping_result is not __NOT_SET:
        return mapping_result

    if first_error is not None:
        raise first_error

    raise TypeError(
        f"Value '{value}' must be of type `"
        + (
            repr(types[0])
            if len(types) == 1
            else " | ".join(
                (
                    (getattr(e, "__name__", None) or str(e) if e is not type(None) else "None")
                    if _get_origin_cached(e) is not Literal
                    else repr(e).replace("typing.", "")
                )
                for e in types
            )
        )
        + f"` but is `{type(value).__name__}`."
    )


@overload
def from_json(s: Union[str, bytes], types: None = ..., /, *, strict: bool = ...) -> Any: ...


@overload
def from_json(s: Union[str, bytes], types: tuple[type[_T], ...], /, *, strict: bool = ...) -> _T: ...


@overload
def from_json(s: Union[str, bytes], types: TypeForm[_T], /, *, strict: bool = ...) -> _T: ...


def from_json(
    s: Union[str, bytes],
    types: Any = None,
    /,
    *,
    strict: bool = False,
) -> Any:
    return from_dict(json.loads(s), types, strict=strict)


def as_dict(value: Any, *, remove_defaults: bool = False, encode: bool = True) -> Dict[str, Any]:
    if not dataclasses.is_dataclass(value):
        raise TypeError("as_dict() should be called on dataclass instances")

    return cast(Dict[str, Any], _as_dict_inner(value, remove_defaults, encode))


def _handle_basic_types(value: Any, _remove_defaults: bool, _encode: bool) -> Any:
    return value


def _has_default_value(field: dataclasses.Field[Any], value: Any) -> bool:
    if field.default is not dataclasses.MISSING:
        return bool(value == field.default)
    if field.default_factory is not dataclasses.MISSING:
        return bool(value == field.default_factory())
    return False


def _handle_dataclass(value: Any, remove_defaults: bool, encode: bool) -> Dict[str, Any]:
    t = type(value)
    fields = __dataclasses_cache.get(t)
    if fields is None:
        fields = dataclasses.fields(t)
        __dataclasses_cache[t] = fields
    return {
        encode_case_for_field_name(t, f) if encode else f.name: _as_dict_inner(
            getattr(value, f.name), remove_defaults, encode
        )
        for f in fields
        if not remove_defaults or not _has_default_value(f, getattr(value, f.name))
    }


def _as_dict_handle_named_tuple(value: Any, remove_defaults: bool, encode: bool) -> List[Any]:
    return [_as_dict_inner(v, remove_defaults, encode) for v in value]


def _as_dict_handle_sequence(value: Any, remove_defaults: bool, encode: bool) -> List[Any]:
    return [_as_dict_inner(v, remove_defaults, encode) for v in value]


def _as_dict_handle_dict(value: Any, remove_defaults: bool, encode: bool) -> Dict[Any, Any]:
    return {
        _as_dict_inner(k, remove_defaults, encode): _as_dict_inner(v, remove_defaults, encode) for k, v in value.items()
    }


def _as_dict_handle_enum(value: enum.Enum, remove_defaults: bool, encode: bool) -> Any:
    return _as_dict_inner(value.value, remove_defaults, encode)


def _as_dict_handle_unknown_type(value: Any, _remove_defaults: bool, _encode: bool) -> Any:
    import warnings

    warnings.warn(f"Can't handle type {type(value)} with value {value!r}")
    return repr(value)


__as_dict_handlers: List[Tuple[Callable[[Any], bool], Callable[[Any, bool, bool], Any]]] = [
    (
        lambda value: type(value) in {int, bool, float, str, NONETYPE},
        _handle_basic_types,
    ),
    (dataclasses.is_dataclass, _handle_dataclass),
    (lambda value: isinstance(value, enum.Enum), _as_dict_handle_enum),
    (
        lambda value: isinstance(value, tuple) and hasattr(value, "_fields"),
        _as_dict_handle_named_tuple,
    ),
    (
        lambda value: isinstance(value, (list, tuple, set, frozenset)),
        _as_dict_handle_sequence,
    ),
    (lambda value: isinstance(value, dict), _as_dict_handle_dict),
    (lambda _value: True, _as_dict_handle_unknown_type),
]


def _as_dict_inner(value: Any, remove_defaults: bool, encode: bool) -> Any:
    t = type(value)
    func = __handlers_cache.get(t)
    if func is None:
        func = __handlers_cache[t] = next(h[1] for h in __as_dict_handlers if h[0](value))

    return func(value, remove_defaults, encode)


class TypeValidationError(Exception):
    def __init__(self, *args: Any, target: Any, errors: Any) -> None:
        super().__init__(*args)
        self.class_ = target.__class__
        self.errors = errors

    def __repr__(self) -> str:
        cls = self.class_
        cls_name = f"{cls.__module__}.{cls.__name__}" if cls.__module__ != "__main__" else cls.__name__
        attrs = ", ".join([repr(v) for v in self.args])
        return f"{cls_name}({attrs}, errors={self.errors!r})"

    def __str__(self) -> str:
        cls = self.class_
        cls_name = f"{cls.__module__}.{cls.__name__}" if cls.__module__ != "__main__" else cls.__name__
        s = cls_name
        return f"{s} (errors = {self.errors!r})"


def __validate_sequence(t: Type[Any], args: Tuple[Any, ...], value: Sequence[Any]) -> List[str]:
    if is_subclass_cached(_get_origin_cached(t) or t, tuple):
        if len(args) == 2 and args[1] is Ellipsis:
            return list(itertools.chain(*(validate_types(args[0], v) for v in value)))

        if len(args) != len(value):
            return [f"Expected {len(args)} values for type {t!r} but got {len(value)}"]

        return list(itertools.chain(*(validate_types(a, v) for a, v in zip(args, value))))

    return list(itertools.chain(*(validate_types(args, v) for v in value)))


def validate_types(expected_types: Union[Type[Any], Tuple[Type[Any], ...], None], value: Any) -> List[str]:
    if expected_types is None:
        return []

    if not isinstance(expected_types, tuple):
        expected_types = (expected_types,)

    result = []

    for t in expected_types:
        args = _get_args_cached(t)
        origin = _get_origin_cached(t)

        if is_union(origin):
            r = validate_types(args, value)
            if r:
                result.extend(r)
                continue

            return []

        if origin is Literal:
            if value in args:
                return []

            result.append(f"Value {value} is not in {args}")
            continue

        if (
            t is Any
            or isinstance(value, origin or t)
            or (
                isinstance(value, Sequence)
                and args
                and is_subclass_cached(origin or t, Sequence)
                and not isinstance(value, str)
            )
        ):
            if isinstance(value, Mapping):
                r = list(
                    itertools.chain(
                        *(
                            itertools.chain(
                                validate_types(args[0] if args else None, n),
                                validate_types(args[1] if args else None, v),
                            )
                            for n, v in value.items()
                        )
                    )
                )
                if r:
                    result.extend(r)
                    continue

                return []

            if isinstance(value, Sequence) and args:
                r = __validate_sequence(t, args, value)
                if r:
                    result.extend(r)
                    continue

                return []

            return []

    if result:
        return result

    types_str = repr(expected_types[0]) if len(expected_types) == 1 else " | ".join(repr(e) for e in expected_types)
    return [f"Expected type {types_str} but got {type(value)}"]


class ValidateMixin:
    def _convert(self) -> None:
        if not dataclasses.is_dataclass(self):
            return

        for f in dataclasses.fields(self):  # type: ignore
            converter = f.metadata.get("convert")
            if converter is not None:
                if inspect.ismethod(converter):
                    setattr(self, f.name, converter(getattr(self, f.name)))
                else:
                    setattr(self, f.name, converter(self, getattr(self, f.name)))

    def _validate(self) -> None:
        if not dataclasses.is_dataclass(self):
            return

        errors = {}  # type: ignore

        type_hints = _get_type_hints_cached(type(self))

        for f in get_dataclass_fields(type(self)):
            validate = f.metadata.get("validate")
            if validate is not None:
                ers = validate(self, getattr(self, f.name))
                if ers:
                    errors[f.name] = ers
            else:
                ers = validate_types(type_hints[f.name], value=getattr(self, f.name))
                if ers:
                    errors[f.name] = ers

        if errors:
            raise TypeValidationError("Dataclass Type Validation Error", target=self, errors=errors)

    def __post_init__(self) -> None:
        self._convert()
        self._validate()


def is_jsonable_dict(o: Any) -> bool:
    return isinstance(o, dict) and "__pickled__" in o


def object_to_jsonable_dict(o: Any) -> dict[str, Any]:
    return {"__pickled__": pickle.dumps(o).hex()}


def jsonable_dict_to_object(d: dict[str, Any]) -> Any:
    if is_jsonable_dict(d):
        return pickle.loads(bytes.fromhex(d["__pickled__"]))
    raise ValueError("Dictionary does not contain pickled data")


def value_to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return object_to_jsonable_dict(value)


def jsonable_to_value(value: Any) -> Any:
    if value is None:
        return None

    if is_jsonable_dict(value):
        return jsonable_dict_to_object(value)

    return value
