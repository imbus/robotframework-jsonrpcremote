import asyncio
import contextlib
import datetime
import io
import math
import pickle
import sys
import threading
import typing
from concurrent.futures import Future, InvalidStateError
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, ClassVar, Mapping, Protocol, Sequence, TypeVar, cast

from robot import result, running
from robot.api import TestSuite, get_model
from robot.api.interfaces import ListenerV3
from robot.conf import RobotSettings
from robot.errors import ExecutionFailed
from robot.output import LOGGER
from robot.running.arguments import ArgInfo, TypeInfo, typeconverters
from robot.running.librarykeywordrunner import LibraryKeywordRunner
from robot.utils import NOT_SET, DotDict, ErrorDetails, escape, text

from jsonrpcpeer import JsonRpcErrorCode, JsonRpcResponseError
from robot_jsonrpcremote_protocol import (
    NOT_DECLARED,
    PICKLED_KEY,
    TYPE_KEY,
    AnyType,
    ArgumentDefinition,
    ArgumentKind,
    KeywordDefinition,
    LibraryDefinition,
    PickleNotAgreedError,
    RobotJsonRpcErrorCode,
    RunKeywordError,
    RunKeywordErrorMode,
    SimpleType,
    ValueCannotTravelError,
    ValueDoesNotFitError,
    ValueFormat,
    resolve_type_name,
    type_name,
)

_T = TypeVar("_T")

# The value format of a client that reads pickles, for a caller that agreed on none.
DEFAULT_VALUE_FORMAT = ValueFormat(pickle.HIGHEST_PROTOCOL, dict_types=(DotDict,))


def _shutting_down() -> JsonRpcResponseError:
    """The error for a command that the stopping server no longer runs."""
    return JsonRpcResponseError(JsonRpcErrorCode.INTERNAL_ERROR, "server is shutting down")


class KeywordFailedError(Exception):
    """A keyword failed; ``error`` is what the server reports for it."""

    def __init__(self, error: RunKeywordError) -> None:
        super().__init__(error.message)
        self.error = error


REPL_SUITE = """\
*** Settings ***
Library  robot_jsonrpcremote_server.InternalRunner
*** Test Cases ***
json_rpc_remote_server_internal_run
    robot_jsonrpcremote_server.InternalRunner.json rpc remote server internal run
"""


class _HookListener(ListenerV3):
    instance: ClassVar["_HookListener"]

    def __init__(
        self, hook_callable: Callable[[], None], log_message_callable: Callable[[result.Message], None]
    ) -> None:
        self._hook_callable = hook_callable
        self._log_message_callable = log_message_callable
        _HookListener.instance = self

    def start_keyword(self, data: running.Keyword, result: result.Keyword) -> None:
        if data.name == "robot_jsonrpcremote_server.InternalRunner.json rpc remote server internal run":
            self._hook_callable()

    def log_message(self, message: result.Message) -> None:
        self._log_message_callable(message)


# `escape` also marks these words, but keywords such as Run Keywords look for them in their arguments.
_CONTROL_WORDS = frozenset(("AND", "ELSE", "ELSE IF", "AS", "WITH NAME"))


def _as_robot_data(value: Any) -> Any:
    """``value`` as data for Robot: it comes out unchanged when Robot resolves it.

    The client has already resolved what it sends, so Robot must not resolve it a second time.
    """
    if isinstance(value, str) and value in _CONTROL_WORDS:
        return value
    return escape(value)


# Robot Framework's names stay for the types of these modules, such as `int`, `Any` or `Sequence`.
_ROBOT_NAMED_MODULES = ("builtins", "typing", "collections.abc")


def _type_text(info: TypeInfo | None) -> str:
    """The text of a type in the library definition: as Robot Framework writes it, with classes named by module."""
    if info is None or not info.name:
        return ""
    if info.is_union:
        return " | ".join(_type_text(member) for member in info.nested or ())
    cls = info.type
    if isinstance(cls, type) and cls.__module__ not in _ROBOT_NAMED_MODULES:
        name = type_name(cls)
    else:
        name = info.name
    if info.nested:
        return f"{name}[{', '.join(_type_text(item) for item in info.nested)}]"
    return name


def _default_of(arg: ArgInfo) -> SimpleType:
    """The default of ``arg`` for the library definition: a JSON scalar as it is, any other value as Libdoc shows it.

    The exact type decides: the members of an ``IntEnum`` are numbers, but Libdoc shows their names.
    """
    value = arg.default
    if type(value) in (type(None), str, bool, int) or (type(value) is float and math.isfinite(value)):
        return cast(SimpleType, value)
    return cast(SimpleType, arg.default_repr)


def _robot_import_library(
    library_token: str | None, name: str, args: Sequence[Any], kw_args: Mapping[str, Any]
) -> LibraryDefinition:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for importing library.")

    # Positional values keep their JSON types. Named values become Robot's "name=value" entries, which
    # Robot converts using the library's __init__ signature, just like in a Library setting.
    robot_args = [_as_robot_data(arg) for arg in args]
    robot_args += [f"{_as_robot_data(key)}={_as_robot_data(str(value))}" for key, value in kw_args.items()]

    context.namespace.import_library(_as_robot_data(name), robot_args, _as_robot_data(library_token))

    lib: "running.TestLibrary" = context.namespace._kw_store.get_library(library_token or name)

    def to_arg_def(arg_spec: "running.ArgumentSpec") -> list[ArgumentDefinition]:
        result: list[ArgumentDefinition] = []
        for arg in arg_spec:
            result.append(
                ArgumentDefinition(
                    name=arg.name,
                    type=_type_text(arg.type),
                    has_default=arg.default is not NOT_SET,
                    default=_default_of(arg) if arg.default is not NOT_SET else None,
                    kind=ArgumentKind.from_value(arg.kind),
                )
            )
        return result

    def to_kw_def(kw: "running.LibraryKeyword") -> KeywordDefinition:
        return KeywordDefinition(
            name=kw.name,
            args=to_arg_def(kw.args),
            doc=kw.doc,
            tags=list(kw.tags),
            source=str(kw.source),
            lineno=kw.lineno,
            return_type=_type_text(kw.args.return_type) or None,
        )

    return LibraryDefinition(
        # The name without the alias: the alias is the token of this import.
        name=lib.real_name,
        keywords=[to_kw_def(kw) for kw in lib.keywords],
        doc=lib.doc,
        doc_format=lib.doc_format,
        scope=lib.scope.name,
        version=lib.version,
        source=str(lib.source),
        lineno=lib.lineno,
    )


def _failure_mode(failure: ExecutionFailed) -> RunKeywordErrorMode | None:
    # In the order in which Robot evaluates the flags.
    if failure.skip:
        return RunKeywordErrorMode.SKIP
    if failure.exit:
        return RunKeywordErrorMode.FATAL
    if failure.continue_on_failure:
        return RunKeywordErrorMode.CONTINUABLE
    return None


def _run_keyword_error(failure: ExecutionFailed) -> RunKeywordError:
    """The error to report for ``failure``: Robot has formatted its message as for a local keyword."""
    # The exception of the keyword, which Robot was handling when it raised the failure. There is none
    # if a library ran the failing keyword itself and Robot aggregated its failures.
    original = failure.__context__
    return RunKeywordError(
        message=failure.message,
        type=type(original).__name__ if original is not None else None,
        traceback=(ErrorDetails(original).traceback or None) if original is not None else None,
        mode=_failure_mode(failure),
    )


# Robot Framework 7.5 gives this converter for a type that it cannot convert, where 7.2 gives none.
_UNKNOWN_CONVERTER: tuple[type, ...] = tuple(
    converter for converter in (getattr(typeconverters, "UnknownConverter", None),) if converter is not None
)


def _hint_part(info: TypeInfo) -> Any:
    """The type hint of a part of a parsed type; raises ``LookupError`` if it is not resolved."""
    if info.is_union:
        return typing.Union[tuple(_hint_part(member) for member in info.nested or ())]
    base = info.type
    if base is None:
        raise LookupError(info.name)
    if info.nested:
        return base[tuple(_hint_part(item) for item in info.nested)]
    return base


def _hint_of(info: TypeInfo | None) -> Any:
    """The type hint of a declared type, or ``NOT_DECLARED`` if there is none or a part of it is not resolved."""
    if info is None or not info.name:
        return NOT_DECLARED
    try:
        return _hint_part(info)
    except (LookupError, TypeError):
        return NOT_DECLARED


def _robot_converts(type_name_: str) -> bool:
    """Whether Robot Framework converts a value to the named type itself, as it would for a local library."""
    try:
        cls = resolve_type_name(type_name_)
    except LookupError:
        return False
    converter = typeconverters.TypeConverter.converter_for(TypeInfo.from_type_hint(cls))
    return converter is not None and not isinstance(converter, _UNKNOWN_CONVERTER)


def _decode_arguments(
    kw: "running.LibraryKeyword",
    args: list[AnyType],
    kwargs: dict[str, AnyType],
    value_format: ValueFormat,
    server_reads_pickles: bool,
) -> tuple[list[Any], dict[str, Any]]:
    """The arguments of a call from the value format of its client; one that is refused fails the call."""
    spec = kw.args
    positional = list(spec.positional)
    types = spec.types

    def decode(data: AnyType, label: str, argument: str | None) -> Any:
        try:
            return value_format.decode(data, _hint_of(types.get(argument) if argument is not None else None))
        except PickleNotAgreedError:
            reason = "no pickles are agreed" if server_reads_pickles else "the server reads no pickles"
            raise JsonRpcResponseError(
                JsonRpcErrorCode.INVALID_PARAMS, f"Argument '{label}' is a pickle, but {reason}."
            ) from None
        except ValueDoesNotFitError as error:
            if _robot_converts(error.type_name) and not (type(data) is dict and _has_marker(data)):
                # Robot Framework converts the value itself, or fails as it would for a local library.
                return data
            raise JsonRpcResponseError(JsonRpcErrorCode.INVALID_PARAMS, error.describe("Argument", label)) from None

    named = set(positional) | set(spec.named_only)
    decoded_args = []
    for index, data in enumerate(args):
        argument = positional[index] if index < len(positional) else spec.var_positional
        decoded_args.append(decode(data, argument or str(index + 1), argument))
    decoded_kwargs = {key: decode(data, key, key if key in named else spec.var_named) for key, data in kwargs.items()}
    return decoded_args, decoded_kwargs


def _has_marker(data: dict[str, Any]) -> bool:
    return PICKLED_KEY in data or TYPE_KEY in data


def _encode_return_value(
    value: Any, declared: TypeInfo | None, value_format: ValueFormat, server_reads_pickles: bool
) -> AnyType:
    try:
        return cast(AnyType, value_format.encode(value, _hint_of(declared)))
    except ValueCannotTravelError as error:
        without_pickles = (
            "the client reads no pickles" if server_reads_pickles else "pickles are turned off with --no-pickles"
        )
        raise JsonRpcResponseError(
            JsonRpcErrorCode.INTERNAL_ERROR,
            f"The return value of type '{error.type_name}' cannot be sent: it is not JSON, and {without_pickles}.",
        ) from None


def _robot_run_keyword(
    library_token: str,
    name: str,
    args: list[AnyType],
    kwargs: dict[str, AnyType],
    value_format: ValueFormat = DEFAULT_VALUE_FORMAT,
    server_reads_pickles: bool = True,
) -> AnyType | None:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for running keyword.")

    lib: "running.TestLibrary" = context.namespace._kw_store.get_library(library_token)

    # A keyword with embedded arguments is called by the name from its definition, with the values as
    # arguments. `find_keywords` also returns other keywords whose patterns fit that name, and it accepts
    # a name with values in it, so for these keywords only the exact name counts.
    kws: "list[running.LibraryKeyword]" = [kw for kw in lib.find_keywords(name) if not kw.embedded or kw.name == name]
    if not kws:
        raise JsonRpcResponseError(
            RobotJsonRpcErrorCode.KEYWORD_NOT_FOUND, f"Keyword '{name}' not found in library '{lib.real_name}'."
        )

    kw: "running.LibraryKeyword" = kws[0]

    decoded_args, decoded_kwargs = _decode_arguments(kw, args, kwargs, value_format, server_reads_pickles)
    runner = LibraryKeywordRunner(kw) if kw.embedded else kw.create_runner(name)
    keyword_data = running.Keyword(
        name=kw.name,
        args=[_as_robot_data(a) for a in decoded_args],
        named_args={_as_robot_data(k): _as_robot_data(v) for k, v in decoded_kwargs.items()},
    )

    keyword_result = result.Keyword(kw.name)
    try:
        r = runner.run(keyword_data, keyword_result, context)
    except ExecutionFailed as failure:
        raise KeywordFailedError(_run_keyword_error(failure)) from None

    return _encode_return_value(r, kw.args.return_type, value_format, server_reads_pickles)


def _robot_finalize_library(library_token: str) -> None:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for finalizing library.")

    # Libraries are imported under their token into the shared keyword store
    # (keyed by name == alias == token). Dropping the entry releases the instance.
    store = context.namespace._kw_store
    lib = store.libraries.pop(library_token, None)
    if lib is None:
        return

    # Best-effort: let the library's scope manager tear the instance down.
    scope_manager = getattr(lib, "scope_manager", None)
    if scope_manager is not None:
        with contextlib.suppress(Exception):
            scope_manager.end_suite()


def _robot_set_log_level(level: str) -> None:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for setting the log level.")

    context.output.set_log_level(level)


class LogMessageSubscriber(Protocol):
    # The log level at which the commands of this subscriber run.
    log_level: str

    def log_message(self, message: str, level: str, html: bool, timestamp: datetime.datetime) -> None: ...


class RobotRemoteContext:
    def __init__(
        self,
        variables: Sequence[str] = (),
        variablefiles: Sequence[str] = (),
        pythonpath: Sequence[str] = (),
        outputdir: str | None = None,
        output: str | None = None,
        report: str | None = None,
        log: str | None = None,
    ) -> None:
        self.variables = variables
        self.variablefiles = variablefiles
        self.pythonpath = pythonpath
        self.outputdir = outputdir
        self.output = output
        self.report = report
        self.log = log

        self._stopped = threading.Event()
        # Guards submitting a command against the drain at the end of the hook loop, so a
        # command is either run by the loop, failed by the drain, or rejected on submit.
        self._lock = threading.Lock()
        # Set once the hook loop has ended; no command is run after that.
        self._closed = False
        self._runner_thread = threading.current_thread()
        self._command_queue: Queue[tuple[Callable[[], Any], Future[Any], LogMessageSubscriber | None]] = Queue()
        # The subscriber whose command is currently executing on the runner thread.
        # Log messages are routed only to it, so concurrent clients don't see each
        # other's logs. No lock needed: only ever accessed on the runner thread.
        self._active_subscriber: LogMessageSubscriber | None = None
        # Whether the last message of the running command reported a failure. Same thread as above.
        self._failure_logged = False

    def _hook_loop(self) -> None:
        # Robot keeps every message of the framework for loggers that register later. All of them have
        # registered by now, and the run of the server does not end, so the messages of every library
        # import would stay. `rebot` turns the cache off the same way.
        LOGGER.disable_message_cache()
        try:
            while not self._stopped.is_set():
                try:
                    command, future, subscriber = self._command_queue.get(timeout=0.1)
                except Empty:
                    continue
                self._active_subscriber = subscriber
                self._failure_logged = False
                try:
                    # Robot has one log level, and the commands of several clients run one after another.
                    _robot_set_log_level(subscriber.log_level if subscriber is not None else "INFO")
                    result = command()
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                finally:
                    self._active_subscriber = None
        finally:
            self._close()

    def _close(self) -> None:
        """Reject further commands and fail the queued ones: no loop will run them anymore."""
        queued: list[Future[Any]] = []
        with self._lock:
            self._closed = True
            while True:
                try:
                    queued.append(self._command_queue.get_nowait()[1])
                except Empty:
                    break
        # Outside the lock: failing a future runs its callbacks.
        for future in queued:
            with contextlib.suppress(InvalidStateError):
                future.set_exception(_shutting_down())

    def _submit(self, command: Callable[[], _T], subscriber: LogMessageSubscriber | None) -> Future[_T]:
        future: Future[_T] = Future()
        with self._lock:
            if self._closed or self._stopped.is_set():
                raise _shutting_down()
            self._command_queue.put((command, future, subscriber))
        return future

    def _log_message(self, message: result.Message) -> None:
        # Robot logs the traceback of a failure at DEBUG right after its FAIL or SKIP message. The
        # error of the keyword call carries the traceback, and the client logs it from there.
        follows_failure, self._failure_logged = self._failure_logged, message.level in ("FAIL", "SKIP")
        if follows_failure and message.level == "DEBUG":
            return

        subscriber = self._active_subscriber
        if subscriber is not None:
            subscriber.log_message(message.message, message.level, message.html, message.timestamp)

    def run(self) -> None:
        # Make the configured pythonpath directories importable so libraries can
        # be loaded from them (e.g. via the server's --pythonpath / -P option).
        for path in self.pythonpath:
            if path and path not in sys.path:
                sys.path.insert(0, str(path))

        curdir = Path.cwd()
        options: dict[str, object] = {
            "variable": list(self.variables),
            "variablefile": list(self.variablefiles),
        }

        settings = RobotSettings(
            options=options,
            outputdir=self.outputdir or str(curdir),
            console="NONE",
            output=self.output,
            log=self.log,
            report=self.report,
            quiet=True,
            listener=[
                _HookListener(self._hook_loop, self._log_message),
            ],
        )

        LOGGER.unregister_console_logger()

        # Robot cuts a long failure message for its report. This server writes no report: it sends the
        # whole message, and the Robot Framework run of the client decides what its report shows.
        text.MAX_ERROR_LINES = None

        with io.StringIO(REPL_SUITE) as suite_io:
            model = get_model(suite_io, curdir=str(curdir).replace("\\", "\\\\"))

        suite = TestSuite.from_model(model)
        suite.configure(**settings.suite_config)
        suite.run(settings)

    def stop(self) -> None:
        # Without the lock: a signal handler calls this on the runner thread, which may
        # hold the lock at that moment.
        self._stopped.set()

    async def import_library(
        self,
        name: str,
        args: Sequence[Any],
        kw_args: Mapping[str, Any],
        library_token: str,
        subscriber: LogMessageSubscriber | None = None,
    ) -> LibraryDefinition:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("import_library cannot be called from the runner thread.")

        future = self._submit(lambda: _robot_import_library(library_token, name, args, kw_args), subscriber)

        return await asyncio.wrap_future(future)

    async def run_keyword(
        self,
        library_token: str,
        name: str,
        args: list[AnyType],
        kwargs: dict[str, AnyType],
        subscriber: LogMessageSubscriber | None = None,
        value_format: ValueFormat = DEFAULT_VALUE_FORMAT,
        server_reads_pickles: bool = True,
    ) -> AnyType | None:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("run_keyword cannot be called from the runner thread.")

        future = self._submit(
            lambda: _robot_run_keyword(library_token, name, args, kwargs, value_format, server_reads_pickles),
            subscriber,
        )

        return await asyncio.wrap_future(future)

    async def finalize_library(self, library_token: str, subscriber: LogMessageSubscriber | None = None) -> None:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("finalize_library cannot be called from the runner thread.")

        future = self._submit(lambda: _robot_finalize_library(library_token), subscriber)

        await asyncio.wrap_future(future)
