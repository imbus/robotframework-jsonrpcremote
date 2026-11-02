from typing import Any

import pytest

from jsonrpcpeer.json_helpers import as_json, from_dict, from_json
from robot_jsonrpcremote_protocol import (
    SET_LOG_LEVEL_NOTIFICATION,
    AnyType,
    ArgumentKind,
    ClientInfo,
    ExitParams,
    FinalizeLibraryParams,
    FinalizeLibraryResult,
    InitializeParams,
    LibraryDefinition,
    RobotJsonRpcErrorCode,
    RunKeywordParams,
    RunKeywordResult,
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
