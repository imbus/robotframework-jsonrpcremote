from dataclasses import dataclass

from typing_extensions import Literal, TypeAlias

SimpleType: TypeAlias = str | int | float | bool | None
AnyType: TypeAlias = SimpleType | list[SimpleType] | dict[str, SimpleType]


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
    doc: str | None = None


@dataclass
class KeywordDefinition:
    name: str
    args: list[ArgumentDefinition]
    doc: str | None = None
    tags: list[str] | None = None
    source: str | None = None


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
    args: list[str | int | float | bool | None]
    kwargs: dict[str, str | int | float | bool | None]


@dataclass
class RunKeywordResult:
    result: AnyType
    error: str | None


@dataclass
class LogParams:
    message: str
    level: Literal["TRACE", "DEBUG", "INFO", "CONSOLE", "HTML", "WARN", "ERROR"] | None = None
    html: bool | None = None
    console: bool | None = None
    timestamp: str | None = None


INITIALIZE_REQUEST = "initialize"
INITIALIZED_NOTIFICATION = "initialized"
SHUTDOWN_REQUEST = "shutdown"
EXIT_NOTIFICATION = "exit"
RUN_KEYWORD_REQUEST = "run_keyword"
LOG_NOTIFICATION = "log"
