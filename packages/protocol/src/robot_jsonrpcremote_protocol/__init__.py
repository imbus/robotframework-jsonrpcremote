from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import TypeAlias

SimpleType: TypeAlias = str | int | float | bool | None
AnyType: TypeAlias = SimpleType | list[SimpleType] | dict[str, SimpleType]


class RobotJsonRpcErrorCode(IntEnum):
    NOT_INITIALIZED = -32000
    KEYWORD_NOT_FOUND = -32001
    ARGUMENT_MISMATCH = -32002


class ArgumentKind(str, Enum):
    POSITIONAL_ONLY = "POSITIONAL_ONLY"
    POSITIONAL_OR_NAMED = "POSITIONAL_OR_NAMED"
    POSITIONAL_ONLY_MARKER = "POSITIONAL_ONLY_MARKER"
    NAMED_ONLY_MARKER = "NAMED_ONLY_MARKER"
    VAR_POSITIONAL = "VAR_POSITIONAL"
    NAMED_ONLY = "NAMED_ONLY"
    VAR_NAMED = "VAR_NAMED"

    def from_value(value: str) -> "ArgumentKind":
        for kind in ArgumentKind:
            if kind.value == value:
                return kind

        raise ValueError(f"Unknown ArgumentKind value: {value}")


class RunKeywordErrorMode(str, Enum):
    CONTINUABLE = "CONTINUABLE"
    FATAL = "FATAL"
    SKIP = "SKIP"


class LogLevel(str, Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CONSOLE = "CONSOLE"
    HTML = "HTML"


@dataclass
class ClientInfo:
    name: str
    version: str


@dataclass
class ClientCapabilities:
    supports_log: bool | None = None
    supports_trace: bool | None = None


@dataclass
class InitializeParams:
    capabilities: ClientCapabilities | None = None
    client_info: ClientInfo | None = None
    initialization_options: AnyType | None = None
    trace: str | None = None


@dataclass
class InitializedParams:
    pass


@dataclass
class ServerInfo:
    name: str
    version: str


@dataclass
class ArgumentDefinition:
    name: str
    type: str | None = None
    has_default: bool | None = None
    default: AnyType | None = None
    required: bool = True
    kind: ArgumentKind | None = None
    doc: str | None = None


@dataclass
class KeywordDefinition:
    name: str
    args: list[ArgumentDefinition]
    doc: str | None = None
    tags: list[str] | None = None
    source: str | None = None
    lineno: int | None = None


@dataclass
class LibraryDefinition:
    name: str
    keywords: list[KeywordDefinition]
    doc: str | None = None
    doc_format: str | None = None
    scope: str | None = None
    version: str | None = None
    source: str | None = None
    lineno: int | None = None


@dataclass
class ServerCapabilities:
    support_exit: bool | None = None
    libraries: list[str] | None = None


@dataclass
class InitializeResult:
    capabilities: ServerCapabilities | None = None
    server_info: ServerInfo | None = None


@dataclass
class ImportLibraryParams:
    name: str
    args: list[AnyType] | None = None
    kw_args: dict[str, AnyType] | None = None


@dataclass
class ImportLibraryResult:
    token: str
    definition: LibraryDefinition


@dataclass
class FinalizeLibraryParams:
    token: str


@dataclass
class FinalizeLibraryResult:
    pass


@dataclass
class ShutdownParams:
    pass


@dataclass
class ShutdownResult:
    pass


@dataclass
class RunKeywordParams:
    library_token: str
    name: str
    args: list[AnyType] | None = None
    kwargs: dict[str, AnyType] | None = None


@dataclass
class RunKeywordError:
    message: str
    type: str | None = None
    traceback: str | None = None
    mode: RunKeywordErrorMode | None = None


@dataclass
class RunKeywordResult:
    result: AnyType | None = None
    error: RunKeywordError | None = None


@dataclass
class LogParams:
    message: str
    level: LogLevel | None = None
    html: bool | None = None
    console: bool | None = None
    timestamp: str | None = None


INITIALIZE_REQUEST = "robot/initialize"
INITIALIZED_NOTIFICATION = "robot/initialized"

IMPORT_LIBRARY_REQUEST = "robot/import_library"
FINALIZE_LIBRARY_REQUEST = "robot/finalize_library"
RUN_KEYWORD_REQUEST = "robot/run_keyword"

SHUTDOWN_REQUEST = "robot/shutdown"
EXIT_NOTIFICATION = "robot/exit"

LOG_NOTIFICATION = "robot/log"
TRACE_NOTIFICATION = "robot/trace"
