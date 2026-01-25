import io
import threading
from concurrent.futures import Future
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, ClassVar, Sequence

from robot import result, running
from robot.api import TestSuite, get_model
from robot.api.interfaces import ListenerV3
from robot.conf import RobotSettings
from robot.output import LOGGER
from robot.reporting import ResultWriter
from robot.utils import NotSet

from jsonrpcpeer.json_helpers import object_to_jsonable_dict
from robot_jsonrpcremote_protocol import ArgumentDefinition, ArgumentKind, KeywordDefinition, LibraryDefinition

REPL_SUITE = """\
*** Settings ***
Library  robot_jsonrpcremote_server.InternalRunner
*** Test Cases ***
json_rpc_remote_server_internal_run
    robot_jsonrpcremote_server.InternalRunner.json rpc remote server internal run
"""


class _HookListener(ListenerV3):
    instance: ClassVar["_HookListener"]

    def __init__(self, hook_callable: Callable[[], None]) -> None:
        self._hook_callable = hook_callable
        _HookListener.instance = self

    def start_keyword(self, data: running.Keyword, result: result.Keyword) -> None:
        if data.name == "robot_jsonrpcremote_server.InternalRunner.json rpc remote server internal run":
            self._hook_callable()


def value_to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return object_to_jsonable_dict(value)


def _robot_import_library(name: str, args: Sequence[str]) -> LibraryDefinition:
    context: "running.context._ExecutionContext" = running.context.EXECUTION_CONTEXTS.current
    if context is None:
        raise RuntimeError("No execution context available for importing library.")

    # TODO: Support kwargs when Robot Framework supports it
    context.namespace.import_library(name, args)

    lib: "running.TestLibrary" = context.namespace._kw_store.get_library(name)
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
        self._command_queue: Queue[tuple[Callable[[], Any], Future[Any]]] = Queue()

    def _hook_callable(self) -> None:
        while not self._stopped.is_set():
            try:
                command, future = self._command_queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                result = command()
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

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
                _HookListener(self._hook_callable),
            ],
        )

        LOGGER.unregister_console_logger()

        with io.StringIO(REPL_SUITE) as suite_io:
            model = get_model(suite_io, curdir=str(curdir).replace("\\", "\\\\"))

        suite = TestSuite.from_model(model)
        suite.configure(**settings.suite_config)
        result = suite.run(settings)

        if settings.log or settings.report or settings.xunit:
            writer = ResultWriter(settings.output if settings.log else result)
            writer.write_results(settings.get_rebot_settings())

    def import_library(self, name: str, args: Sequence[str]) -> LibraryDefinition:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("import_library cannot be called from the runner thread.")

        future: Future[LibraryDefinition] = Future()
        self._command_queue.put((lambda: _robot_import_library(name, args), future))

        return future.result()

    def run_keyword(self, keyword_name: str, args: Sequence[str]) -> object | None:
        if threading.current_thread() == self._runner_thread:
            raise RuntimeError("run_keyword cannot be called from the runner thread.")

        return None  # Placeholder for actual keyword execution

    def stop(self) -> None:
        self._stopped.set()


if __name__ == "__main__":
    context = RobotRemoteContext()
    context.run()
