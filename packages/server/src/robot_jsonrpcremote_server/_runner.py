import asyncio
import datetime
import io
import threading
from concurrent.futures import Future
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, ClassVar, Protocol, Sequence, cast

from robot import result, running
from robot.api import TestSuite, get_model
from robot.api.interfaces import ListenerV3
from robot.conf import RobotSettings
from robot.output import LOGGER
from robot.reporting import ResultWriter
from robot.utils import NotSet

from jsonrpcpeer.json_helpers import jsonable_to_value, value_to_jsonable
from robot_jsonrpcremote_protocol import AnyType, ArgumentDefinition, ArgumentKind, KeywordDefinition, LibraryDefinition

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


def _robot_import_library(library_token: str | None, name: str, args: Sequence[Any]) -> LibraryDefinition:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for importing library.")

    # TODO: Support kwargs when Robot Framework supports it
    context.namespace.import_library(name, args, library_token)

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
                    has_default=not isinstance(arg.default, NotSet),
                    default=value_to_jsonable(arg.default) if not isinstance(arg.default, NotSet) else None,
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


def _robot_run_keyword(
    library_token: str, name: str, args: list[AnyType], kwargs: dict[str, AnyType]
) -> AnyType | None:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for running keyword.")

    lib: "running.TestLibrary" = context.namespace._kw_store.get_library(library_token)
    if lib is None:
        raise RuntimeError(f"Library with token '{library_token}' is not imported.")

    kws: "running.LibraryKeyword" = lib.find_keywords(name)
    if kws is None:
        raise RuntimeError(f"Keyword '{name}' not found in library '{lib.name}'.")
    if len(kws) > 1:
        raise RuntimeError(f"Multiple keywords named '{name}' found in library '{lib.name}'.")

    kw: "running.LibraryKeyword" = kws[0]

    runner = kw.create_runner(name)
    keyword_data = running.Keyword(
        name=kw.name,
        args=[jsonable_to_value(a) for a in args],
        named_args={jsonable_to_value(k): jsonable_to_value(v) for k, v in kwargs.items()},
    )

    keyword_result = result.Keyword(kw.name)
    r = runner.run(keyword_data, keyword_result, context)

    return cast(AnyType, value_to_jsonable(r))


class LogMessageSubscriber(Protocol):
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
        self._runner_thread = threading.current_thread()
        self._command_queue: Queue[tuple[Callable[[], Any], Future[Any], LogMessageSubscriber | None]] = Queue()
        # The subscriber whose command is currently executing on the runner thread.
        # Log messages are routed only to it, so concurrent clients don't see each
        # other's logs. No lock needed: only ever accessed on the runner thread.
        self._active_subscriber: LogMessageSubscriber | None = None

    def _hook_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                command, future, subscriber = self._command_queue.get(timeout=0.1)
            except Empty:
                continue
            self._active_subscriber = subscriber
            try:
                result = command()
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            finally:
                self._active_subscriber = None

    def _log_message(self, message: result.Message) -> None:
        subscriber = self._active_subscriber
        if subscriber is not None:
            subscriber.log_message(message.message, message.level, message.html, message.timestamp)

    def run(self) -> None:
        curdir = Path.cwd()
        options: dict[str, object] = {}

        settings = RobotSettings(
            options=options,
            outputdir=str(curdir),
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

        with io.StringIO(REPL_SUITE) as suite_io:
            model = get_model(suite_io, curdir=str(curdir).replace("\\", "\\\\"))

        suite = TestSuite.from_model(model)
        suite.configure(**settings.suite_config)
        run_result = suite.run(settings)

        if settings.log or settings.report or settings.xunit:
            writer = ResultWriter(settings.output if settings.log else run_result)
            writer.write_results(settings.get_rebot_settings())

    def stop(self) -> None:
        self._stopped.set()

    async def import_library(
        self, name: str, args: Sequence[Any], library_token: str, subscriber: LogMessageSubscriber | None = None
    ) -> LibraryDefinition:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("import_library cannot be called from the runner thread.")

        future: Future[LibraryDefinition] = Future()
        self._command_queue.put((lambda: _robot_import_library(library_token, name, args), future, subscriber))

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

        future: Future[AnyType] = Future()
        self._command_queue.put((lambda: _robot_run_keyword(library_token, name, args, kwargs), future, subscriber))

        return await asyncio.wrap_future(future)
