from dataclasses import dataclass
from enum import Enum, IntEnum

from typing_extensions import TypeAlias

SimpleType: TypeAlias = str | int | float | bool | None
AnyType: TypeAlias = SimpleType | list[SimpleType] | dict[str, SimpleType]


class RobotJsonRpcErrorCode(IntEnum):
    NOT_INITIALIZED = -32000
    KEYWORD_NOT_FOUND = -32001
    ARGUMENT_MISMATCH = -32002


class ArgumentKind(str, Enum):
    POSITIONAL_ONLY = "POSITIONAL_ONLY"
    POSITIONAL_OR_NAMED = "POSITIONAL_OR_NAMED"
    VAR_POSITIONAL = "VAR_POSITIONAL"
    NAMED_ONLY = "NAMED_ONLY"
    VAR_NAMED = "VAR_NAMED"


class RunKeywordErrorMode(str, Enum):
    CONTINUABLE = "CONTINUABLE"
    FATAL = "FATAL"
    SKIP = "SKIP"


class LogLevel(str, Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    CONSOLE = "CONSOLE"
    HTML = "HTML"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class ClientInfo:
    name: str
    version: str


@dataclass
class ClientCapabilities:
    pass


@dataclass
class InitializeParams:
    capabilities: ClientCapabilities | None = None
    client_info: ClientInfo | None = None
    initialization_options: AnyType | None = None
    trace: str | None = None

    library_name: str | None = None
    library_args: list[AnyType] | None = None
    library_kw_args: dict[str, AnyType] | None = None


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
    source: str | None = None


@dataclass
class ServerCapabilities:
    pass


@dataclass
class InitializeResult:
    library_definition: LibraryDefinition
    capabilities: ServerCapabilities | None = None
    server_info: ServerInfo | None = None


@dataclass
class ShutdownParams:
    pass


@dataclass
class ShutdownResult:
    pass


@dataclass
class RunKeywordParams:
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


INITIALIZE_REQUEST = "initialize"
INITIALIZED_NOTIFICATION = "initialized"
SHUTDOWN_REQUEST = "shutdown"
EXIT_NOTIFICATION = "exit"
RUN_KEYWORD_REQUEST = "run_keyword"
LOG_NOTIFICATION = "log"
