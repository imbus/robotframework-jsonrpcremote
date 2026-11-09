"""The client's side of the value format: the agreement on pickles, and how arguments and return values travel."""

import asyncio
import os
import pickle
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fake_server import FakeServer
from robot.utils import DotDict
from value_types import Color, Point, Widget

from JsonRpcRemote import JsonRpcRemote
from robot_jsonrpcremote_protocol import (
    IMPORT_LIBRARY_REQUEST,
    INITIALIZE_REQUEST,
    PICKLED_KEY,
    RUN_KEYWORD_REQUEST,
    TYPE_KEY,
    ArgumentDefinition,
    ArgumentKind,
    ImportLibraryResult,
    KeywordDefinition,
    LibraryDefinition,
    RunKeywordResult,
)

# Unpickling it would import a module that does not exist.
_PICKLE_OF_A_MISSING_MODULE = {PICKLED_KEY: b"cmodule_that_does_not_exist\nThing\n.".hex()}


@pytest.fixture
def server() -> Iterator[FakeServer]:
    with FakeServer() as fake:
        yield fake


@pytest.fixture
def connect(server: FakeServer) -> Iterator[Any]:
    clients: list[JsonRpcRemote] = []

    def connect(**options: Any) -> JsonRpcRemote:
        client = JsonRpcRemote(server.uri, "FakeLib", rpc_timeout=5, **options)
        clients.append(client)
        return client

    yield connect
    for client in clients:
        client._stop_session()


def _call(remote: JsonRpcRemote, *args: Any) -> Any:
    """Run the fake library's ``Echo`` keyword the way Robot Framework calls it."""
    return asyncio.run(remote.run_keyword("Echo", list(args), {}))


def _define(server: FakeServer, *args: tuple[str, str], return_type: str | None = None) -> None:
    """Let the fake server define the keyword ``Echo`` with these arguments, as names and type texts."""
    arguments = [ArgumentDefinition(name=name, type=text, kind=ArgumentKind.POSITIONAL_OR_NAMED) for name, text in args]
    keyword = KeywordDefinition(name="Echo", args=arguments, return_type=return_type)
    definition = LibraryDefinition(name="FakeLib", keywords=[keyword])
    server.script(IMPORT_LIBRARY_REQUEST, ImportLibraryResult(token="t", definition=definition))


def _params_of(server: FakeServer, method: str) -> list[Any]:
    return [params for request, params in zip(server.requests, server.params) if request == method]


# --- the agreement --------------------------------------------------------------------------------------------------


def test_the_client_states_the_highest_pickle_protocol(server: FakeServer, connect: Any) -> None:
    connect()

    [initialize] = _params_of(server, INITIALIZE_REQUEST)
    assert initialize["capabilities"]["pickle_protocol"] == pickle.HIGHEST_PROTOCOL


def test_rpc_pickles_false_states_no_pickle_protocol(server: FakeServer, connect: Any) -> None:
    connect(rpc_pickles=False)

    [initialize] = _params_of(server, INITIALIZE_REQUEST)
    assert initialize["capabilities"].get("pickle_protocol") is None


def test_rpc_pickles_is_not_forwarded(server: FakeServer, connect: Any) -> None:
    connect(rpc_pickles=False, greeting="hi")

    [import_library] = _params_of(server, IMPORT_LIBRARY_REQUEST)
    assert import_library["kw_args"] == {"greeting": "hi"}


# --- arguments and return values ------------------------------------------------------------------------------------


def test_lists_and_dicts_reach_the_server_as_plain_json(server: FakeServer, connect: Any) -> None:
    remote = connect()

    _call(remote, [1, 2])
    _call(remote, DotDict(a=1))

    assert [params["args"] for params in _params_of(server, RUN_KEYWORD_REQUEST)] == [[[1, 2]], [{"a": 1}]]


def test_a_tuple_is_pickled_when_pickles_are_agreed(server: FakeServer, connect: Any) -> None:
    remote = connect()

    _call(remote, (1, 2))

    [run] = _params_of(server, RUN_KEYWORD_REQUEST)
    assert set(run["args"][0]) == {PICKLED_KEY}


def test_an_argument_that_needs_a_pickle_fails_before_it_is_sent(server: FakeServer, connect: Any) -> None:
    server.pickle_protocol = None
    remote = connect()

    with pytest.raises(TypeError) as error:
        _call(remote, Widget("w"))

    assert str(error.value) == (
        "Argument 'message' of type 'value_types.Widget' cannot be sent: it is not JSON, "
        "and the server reads no pickles."
    )
    assert _params_of(server, RUN_KEYWORD_REQUEST) == []


def test_with_rpc_pickles_false_the_failure_names_the_option(connect: Any) -> None:
    remote = connect(rpc_pickles=False)

    with pytest.raises(TypeError, match=r"and rpc_pickles is off\.$"):
        _call(remote, Widget("w"))


def test_a_pickle_from_the_server_without_the_agreement_fails(server: FakeServer, connect: Any) -> None:
    remote = connect(rpc_pickles=False)
    server.script(RUN_KEYWORD_REQUEST, RunKeywordResult(result=_PICKLE_OF_A_MISSING_MODULE))

    # A TypeError, not the ModuleNotFoundError of unpickling it.
    with pytest.raises(TypeError, match=r"^The server sent the return value as a pickle, but rpc_pickles is off\.$"):
        _call(remote, "x")


def test_a_typed_value_without_a_declared_type_comes_back_as_its_class(server: FakeServer, connect: Any) -> None:
    remote = connect()
    server.script(RUN_KEYWORD_REQUEST, RunKeywordResult(result={TYPE_KEY: "value_types.Point", "x": 1, "y": 2}))

    assert _call(remote, "x") == Point(1, 2)


# --- declared types ------------------------------------------------------------------------------------------------


def test_get_keyword_types_gives_the_installed_classes(server: FakeServer, connect: Any) -> None:
    _define(server, ("color", "value_types.Color"), ("at", "list[value_types.Point] | None"))

    types = connect().get_keyword_types("Echo")

    assert types == {"color": Color, "at": list[Point] | None}


def test_a_type_that_does_not_resolve_stays_a_text(server: FakeServer, connect: Any) -> None:
    _define(server, ("at", "notinstalled.Point"), ("points", "list[notinstalled.Point]"))

    types = connect().get_keyword_types("Echo")

    assert types == {"at": "notinstalled.Point", "points": "list[notinstalled.Point]"}


def test_an_enum_converted_by_robot_framework_reaches_the_server_as_its_name(
    server: FakeServer, tmp_path: Path
) -> None:
    # Robot Framework converts `red` on the client, since the client gives it the class of the declared type.
    _define(server, ("message", "value_types.Color"))
    suite = tmp_path / "enum.robot"
    suite.write_text(
        "*** Settings ***\n"
        f"Library    JsonRpcRemote    {server.uri}    FakeLib\n\n"
        "*** Test Cases ***\nColor By Its Value\n    Echo    red\n",
        encoding="utf-8",
    )

    run = subprocess.run(
        [sys.executable, "-m", "robot", "--output", "NONE", "--report", "NONE", "--log", "NONE", str(suite)],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), os.environ.get("PYTHONPATH", "")]),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert run.returncode == 0, run.stdout + run.stderr
    assert [params["args"] for params in _params_of(server, RUN_KEYWORD_REQUEST)] == [["RED"]]


def test_a_declared_return_value_becomes_its_class(server: FakeServer, connect: Any) -> None:
    server.pickle_protocol = None
    _define(server, ("message", ""), return_type="value_types.Point")
    remote = connect()
    server.script(RUN_KEYWORD_REQUEST, RunKeywordResult(result={"x": 1, "y": 2}))

    assert _call(remote, "x") == Point(1, 2)


def test_a_declared_enum_argument_goes_as_its_name_with_pickles(server: FakeServer, connect: Any) -> None:
    _define(server, ("message", "value_types.Color"))
    remote = connect()

    _call(remote, Color.RED)

    [run] = _params_of(server, RUN_KEYWORD_REQUEST)
    assert run["args"] == ["RED"]


def test_a_return_value_of_a_class_that_is_not_installed_fails(server: FakeServer, connect: Any) -> None:
    remote = connect()
    server.script(RUN_KEYWORD_REQUEST, RunKeywordResult(result={TYPE_KEY: "notinstalled.Point", "x": 1}))

    with pytest.raises(ValueError, match=r"^Return value '") as error:
        _call(remote, "x")

    assert str(error.value).endswith(
        "' (dictionary) cannot be converted to notinstalled.Point: "
        "it cannot be imported: No module named 'notinstalled'"
    )


def test_a_return_value_that_does_not_fit_its_type_fails(server: FakeServer, connect: Any) -> None:
    _define(server, ("message", ""), return_type="value_types.Point")
    remote = connect()
    server.script(RUN_KEYWORD_REQUEST, RunKeywordResult(result={"x": 1}))

    with pytest.raises(ValueError, match=r"^Return value ") as error:
        _call(remote, "x")

    assert str(error.value) == (
        "Return value '{'x': 1}' (dictionary) cannot be converted to value_types.Point: missing field 'y'"
    )
