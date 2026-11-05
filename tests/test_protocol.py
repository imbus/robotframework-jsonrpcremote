import asyncio
from typing import Any

import pytest
from connected_peers import connected_peers

from jsonrpcpeer.json_helpers import as_json, from_dict, from_json
from robot_jsonrpcremote_protocol import (
    SET_LOG_LEVEL_NOTIFICATION,
    AnyType,
    ArgumentKind,
    ClientEndpoint,
    ClientInfo,
    ExitParams,
    FinalizeLibraryParams,
    FinalizeLibraryResult,
    ImportLibraryParams,
    ImportLibraryResult,
    InitializedParams,
    InitializeParams,
    InitializeResult,
    LibraryDefinition,
    LogParams,
    RobotJsonRpcErrorCode,
    RunKeywordParams,
    RunKeywordResult,
    ServerEndpoint,
    SetLogLevelParams,
    ShutdownParams,
    ShutdownResult,
)


def test_error_codes_of_the_protocol() -> None:
    assert {code.name: code.value for code in RobotJsonRpcErrorCode} == {
        "NOT_INITIALIZED": -32000,
        "KEYWORD_NOT_FOUND": -32001,
    }


def test_argument_kind_value_lookup() -> None:
    assert ArgumentKind("VAR_NAMED") is ArgumentKind.VAR_NAMED


def test_argument_kind_from_value() -> None:
    assert ArgumentKind.from_value("POSITIONAL_ONLY") is ArgumentKind.POSITIONAL_ONLY


def test_argument_kind_from_value_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown ArgumentKind"):
        ArgumentKind.from_value("nope")


def test_run_keyword_params_roundtrip_preserves_arg_order() -> None:
    data = {"library_token": "t", "name": "kw", "args": [3, 1, 1, 2], "kwargs": {"a": 1}}
    params = from_dict(data, RunKeywordParams)
    assert params.library_token == "t"
    assert params.name == "kw"
    assert params.args == [3, 1, 1, 2]
    assert params.kwargs == {"a": 1}


def test_library_definition_nested_from_dict() -> None:
    data = {
        "name": "Lib",
        "keywords": [
            {"name": "kw", "args": [{"name": "a", "type": "str", "kind": "VAR_NAMED"}]},
        ],
    }
    lib = from_dict(data, LibraryDefinition)
    assert lib.name == "Lib"
    assert lib.keywords[0].name == "kw"
    arg = lib.keywords[0].args[0]
    assert arg.name == "a"
    assert arg.type == "str"
    assert arg.kind is ArgumentKind.VAR_NAMED


NESTED_VALUES = [[{"id": 1}], {"a": [1, 2]}, [[1, 2]], [{}]]


@pytest.mark.parametrize("value", NESTED_VALUES)
def test_any_type_keeps_nested_values(value: Any) -> None:
    assert from_dict(value, AnyType) == value


@pytest.mark.parametrize("value", NESTED_VALUES)
def test_run_keyword_params_keep_nested_values(value: Any) -> None:
    data = {"library_token": "t", "name": "kw", "args": [value], "kwargs": {"a": value}}
    params = from_dict(data, RunKeywordParams)
    assert params.args == [value]
    assert params.kwargs == {"a": value}


@pytest.mark.parametrize("value", NESTED_VALUES)
def test_run_keyword_result_keeps_nested_values(value: Any) -> None:
    assert from_dict({"result": value}, RunKeywordResult).result == value


def test_any_type_keeps_a_boolean() -> None:
    assert from_dict(True, AnyType) is True


def test_initialize_params_json_roundtrip() -> None:
    params = InitializeParams(client_info=ClientInfo(name="c", version="1"))
    restored = from_json(as_json(params), InitializeParams)
    assert restored.client_info == ClientInfo(name="c", version="1")


def test_initialize_params_carry_the_log_level() -> None:
    assert from_json(as_json(InitializeParams(log_level="DEBUG")), InitializeParams).log_level == "DEBUG"
    assert from_json(as_json(InitializeParams()), InitializeParams).log_level is None


def test_set_log_level_notification_roundtrip() -> None:
    assert SET_LOG_LEVEL_NOTIFICATION == "robot/set_log_level"
    assert from_json(as_json(SetLogLevelParams(log_level="TRACE")), SetLogLevelParams).log_level == "TRACE"


def test_finalize_library_params_roundtrip() -> None:
    params = from_json(as_json(FinalizeLibraryParams(token="lib_1")), FinalizeLibraryParams)
    assert params.token == "lib_1"


@pytest.mark.parametrize("cls", [FinalizeLibraryResult, ShutdownParams, ShutdownResult, ExitParams])
def test_empty_termination_payloads_roundtrip(cls: type) -> None:
    # The empty handshake payloads serialize to {} and decode back to an instance.
    assert as_json(cls()) == "{}"
    assert isinstance(from_dict({}, cls), cls)


# --- the definitions of both sides ----------------------------------------------


@pytest.mark.parametrize(
    ("method", "params", "sent", "wire_name", "answer", "result_type"),
    [
        (
            "initialize",
            InitializeParams(log_level="DEBUG"),
            {"log_level": "DEBUG"},
            "robot/initialize",
            {},
            InitializeResult,
        ),
        (
            "import_library",
            ImportLibraryParams(name="Lib"),
            {"name": "Lib"},
            "robot/import_library",
            {"token": "t", "definition": {"name": "Lib", "keywords": []}},
            ImportLibraryResult,
        ),
        (
            "run_keyword",
            RunKeywordParams(library_token="t", name="Keyword"),
            {"library_token": "t", "name": "Keyword"},
            "robot/run_keyword",
            {"result": 1},
            RunKeywordResult,
        ),
        (
            "finalize_library",
            FinalizeLibraryParams(token="t"),
            {"token": "t"},
            "robot/finalize_library",
            {},
            FinalizeLibraryResult,
        ),
        ("shutdown", ShutdownParams(), {}, "robot/shutdown", {}, ShutdownResult),
    ],
    ids=["initialize", "import_library", "run_keyword", "finalize_library", "shutdown"],
)
async def test_requests_of_the_server_definition(
    method: str, params: Any, sent: Any, wire_name: str, answer: Any, result_type: type[Any]
) -> None:
    seen: list[Any] = []

    async def handler(raw: Any) -> Any:
        seen.append(raw)
        return answer

    async with connected_peers() as peers:
        peers.right.register_request_handler(wire_name, handler)
        result = await asyncio.wait_for(getattr(peers.left.remote(ServerEndpoint), method)(params), 2)

    assert isinstance(result, result_type)
    assert seen == [sent]


@pytest.mark.parametrize(
    ("method", "params", "sent", "wire_name"),
    [
        ("initialized", InitializedParams(), {}, "robot/initialized"),
        ("set_log_level", SetLogLevelParams(log_level="DEBUG"), {"log_level": "DEBUG"}, "robot/set_log_level"),
        ("exit", ExitParams(), {}, "robot/exit"),
    ],
    ids=["initialized", "set_log_level", "exit"],
)
async def test_notifications_of_the_server_definition(method: str, params: Any, sent: Any, wire_name: str) -> None:
    seen: asyncio.Queue[Any] = asyncio.Queue()

    async def handler(raw: Any) -> None:
        await seen.put(raw)

    async with connected_peers() as peers:
        peers.right.register_notification_handler(wire_name, handler)
        await getattr(peers.left.remote(ServerEndpoint), method)(params)
        received = await asyncio.wait_for(seen.get(), 2)

    assert received == sent


async def test_log_of_the_client_definition() -> None:
    seen: asyncio.Queue[Any] = asyncio.Queue()

    async def handler(raw: Any) -> None:
        await seen.put(raw)

    async with connected_peers() as peers:
        peers.left.register_notification_handler("robot/log", handler)
        await peers.right.remote(ClientEndpoint).log(LogParams(message="from the server"))
        received = await asyncio.wait_for(seen.get(), 2)

    assert received == {"message": "from the server"}


def test_server_definition_names_a_missing_method() -> None:
    class LeavesOutRunKeyword(ServerEndpoint):
        pass

    with pytest.raises(TypeError, match="run_keyword"):
        LeavesOutRunKeyword()  # type: ignore[abstract]
