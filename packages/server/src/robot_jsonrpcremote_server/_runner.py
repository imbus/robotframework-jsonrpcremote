import asyncio
import contextlib
import datetime
import io
import sys
import threading
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
from robot.running.librarykeywordrunner import LibraryKeywordRunner
from robot.utils import NOT_SET, ErrorDetails, escape, text

from jsonrpcpeer import JsonRpcErrorCode, JsonRpcResponseError
from jsonrpcpeer.json_helpers import jsonable_to_value, value_to_jsonable
from robot_jsonrpcremote_protocol import (
    AnyType,
    ArgumentDefinition,
    ArgumentKind,
    KeywordDefinition,
    LibraryDefinition,
    RobotJsonRpcErrorCode,
    RunKeywordError,
    RunKeywordErrorMode,
)

_T = TypeVar("_T")


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
    if lib is None:
        raise RuntimeError(f"Library '{name}' could not be imported.")

    def to_arg_def(arg_spec: "running.ArgumentSpec") -> list[ArgumentDefinition]:
        result: list[ArgumentDefinition] = []
        for arg in arg_spec:
            result.append(
                ArgumentDefinition(
                    name=arg.name,
                    type=str(arg.type),
                    has_default=arg.default is not NOT_SET,
                    default=value_to_jsonable(arg.default) if arg.default is not NOT_SET else None,
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
        )

    return LibraryDefinition(
        name=lib.name,
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


def _robot_run_keyword(
    library_token: str, name: str, args: list[AnyType], kwargs: dict[str, AnyType]
) -> AnyType | None:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for running keyword.")

    lib: "running.TestLibrary" = context.namespace._kw_store.get_library(library_token)
    if lib is None:
        raise RuntimeError(f"Library with token '{library_token}' is not imported.")

    # A keyword with embedded arguments is called by the name from its definition, with the values as
    # arguments. `find_keywords` also returns other keywords whose patterns fit that name, and it accepts
    # a name with values in it, so for these keywords only the exact name counts.
    kws: "list[running.LibraryKeyword]" = [kw for kw in lib.find_keywords(name) if not kw.embedded or kw.name == name]
    if not kws:
        raise JsonRpcResponseError(
            RobotJsonRpcErrorCode.KEYWORD_NOT_FOUND, f"Keyword '{name}' not found in library '{lib.real_name}'."
        )

    kw: "running.LibraryKeyword" = kws[0]

    runner = LibraryKeywordRunner(kw) if kw.embedded else kw.create_runner(name)
    keyword_data = running.Keyword(
        name=kw.name,
        args=[_as_robot_data(jsonable_to_value(a)) for a in args],
        named_args={
            _as_robot_data(jsonable_to_value(k)): _as_robot_data(jsonable_to_value(v)) for k, v in kwargs.items()
        },
    )

    keyword_result = result.Keyword(kw.name)
    try:
        r = runner.run(keyword_data, keyword_result, context)
    except ExecutionFailed as failure:
        raise KeywordFailedError(_run_keyword_error(failure)) from None

    return cast(AnyType, value_to_jsonable(r))


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
    ) -> AnyType | None:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("run_keyword cannot be called from the runner thread.")

        future = self._submit(lambda: _robot_run_keyword(library_token, name, args, kwargs), subscriber)

        return await asyncio.wrap_future(future)

    async def finalize_library(self, library_token: str, subscriber: LogMessageSubscriber | None = None) -> None:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("finalize_library cannot be called from the runner thread.")

        future = self._submit(lambda: _robot_finalize_library(library_token), subscriber)

        await asyncio.wrap_future(future)
