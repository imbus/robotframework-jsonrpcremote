"""Endpoint definitions: implementing them with ``attach_endpoint`` and calling them with ``remote``.

Where a test checks the messages themselves, the other side registers plain handlers, so that the test does
not depend on the definition it checks.
"""

import asyncio
import importlib
import json
from abc import abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, assert_type, cast

import pytest
import pytest_asyncio
from connected_peers import ConnectedPeers, connected_peers

from jsonrpcpeer import (
    JsonRpcConnectionClosedError,
    JsonRpcEndpoint,
    JsonRpcErrorCode,
    JsonRpcMethodAlreadyRegisteredError,
    JsonRpcPeer,
    JsonRpcResponseError,
    rpc_notification,
    rpc_request,
)


@dataclass
class AddParams:
    a: int
    b: int


@dataclass
class AddResult:
    sum: int


@dataclass
class Note:
    text: str


class Calculator(JsonRpcEndpoint):
    @rpc_request("calc/add")
    @abstractmethod
    async def add(self, params: AddParams) -> AddResult: ...

    @rpc_notification("calc/note")
    @abstractmethod
    async def note(self, params: Note) -> None: ...


class Console(JsonRpcEndpoint):
    @rpc_notification("console/print")
    @abstractmethod
    async def print(self, params: Note) -> None: ...


class WithDefault(JsonRpcEndpoint):
    @rpc_request("default/answer")
    async def answer(self, params: Note) -> Note:
        return Note("from the definition")


class WorkingCalculator(Calculator):
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.notes: list[Any] = []

    async def add(self, params: AddParams) -> AddResult:
        self.added.append(params)
        return AddResult(params.a + params.b)

    async def note(self, params: Note) -> None:
        self.notes.append(params)


class WorkingConsole(Console):
    def __init__(self) -> None:
        self.printed: list[Any] = []

    async def print(self, params: Note) -> None:
        self.printed.append(params)


@pytest_asyncio.fixture
async def connected() -> AsyncIterator[ConnectedPeers]:
    async with connected_peers() as peers:
        yield peers


async def _wait_until(condition: Callable[[], bool]) -> None:
    for _ in range(2000):
        if condition():
            return
        await asyncio.sleep(0.001)
    raise AssertionError("The condition did not become true in time")


# --- a definition, and implementing it ----------------------------------------


def test_subclass_that_leaves_out_a_method_cannot_be_created() -> None:
    class OnlyAdds(Calculator):
        async def add(self, params: AddParams) -> AddResult:
            return AddResult(0)

    with pytest.raises(TypeError, match="note"):
        OnlyAdds()  # type: ignore[abstract]


def test_subclass_with_all_methods_can_be_created() -> None:
    assert isinstance(WorkingCalculator(), Calculator)


async def test_override_answers_a_request_with_converted_params(connected: ConnectedPeers) -> None:
    calculator = WorkingCalculator()
    connected.right.attach_endpoint(calculator)

    result = await asyncio.wait_for(connected.left.send_request("calc/add", {"a": 1, "b": 2}), 2)

    assert result == {"sum": 3}
    assert calculator.added == [AddParams(1, 2)]


async def test_override_answers_a_notification_with_converted_params(connected: ConnectedPeers) -> None:
    calculator = WorkingCalculator()
    connected.right.attach_endpoint(calculator)

    await connected.left.send_notification("calc/note", {"text": "hello"})
    await _wait_until(lambda: bool(calculator.notes))

    assert calculator.notes == [Note("hello")]


async def test_attached_endpoint_knows_its_peer(connected: ConnectedPeers) -> None:
    calculator = WorkingCalculator()
    assert calculator.rpc_peer is None

    connected.right.attach_endpoint(calculator)

    assert calculator.rpc_peer is connected.right


async def test_default_implementation_answers(connected: ConnectedPeers) -> None:
    class UsesTheDefault(WithDefault):
        pass

    connected.right.attach_endpoint(UsesTheDefault())

    result = await asyncio.wait_for(connected.left.send_request("default/answer", {"text": "x"}), 2)

    assert result == {"text": "from the definition"}


async def test_override_without_an_annotation_gets_the_params_as_they_arrived(connected: ConnectedPeers) -> None:
    seen: list[Any] = []

    class Untyped(WorkingCalculator):
        async def add(self, params):  # type: ignore[no-untyped-def]
            seen.append(params)
            return AddResult(0)

    connected.right.attach_endpoint(Untyped())

    await asyncio.wait_for(connected.left.send_request("calc/add", {"a": 1, "b": 2}), 2)

    assert seen == [{"a": 1, "b": 2}]


async def test_further_subclass_overrides_again(connected: ConnectedPeers) -> None:
    class Doubling(WorkingCalculator):
        async def add(self, params: AddParams) -> AddResult:
            return AddResult((params.a + params.b) * 2)

    connected.right.attach_endpoint(Doubling())

    result = await asyncio.wait_for(connected.left.send_request("calc/add", {"a": 1, "b": 2}), 2)

    assert result == {"sum": 6}


async def test_override_with_a_mark_of_its_own_replaces_the_name(connected: ConnectedPeers) -> None:
    class Renamed(WorkingCalculator):
        @rpc_request("calc/renamed")
        async def add(self, params: AddParams) -> AddResult:
            return AddResult(7)

    connected.right.attach_endpoint(Renamed())

    assert await asyncio.wait_for(connected.left.send_request("calc/renamed", {"a": 1, "b": 2}), 2) == {"sum": 7}
    with pytest.raises(JsonRpcResponseError) as error:
        await asyncio.wait_for(connected.left.send_request("calc/add", {"a": 1, "b": 2}), 2)
    assert error.value.code == JsonRpcErrorCode.METHOD_NOT_FOUND


async def test_marked_method_without_a_separate_definition(connected: ConnectedPeers) -> None:
    class NoDefinition(JsonRpcEndpoint):
        @rpc_request("own/answer")
        async def answer(self, params: Note) -> Note:
            return Note(params.text.upper())

    connected.right.attach_endpoint(NoDefinition())

    assert await asyncio.wait_for(connected.left.send_request("own/answer", {"text": "x"}), 2) == {"text": "X"}


async def test_marked_plain_method_answers(connected: ConnectedPeers) -> None:
    class Plain(JsonRpcEndpoint):
        def __init__(self) -> None:
            self.notes: list[Any] = []

        @rpc_request("plain/answer")
        def answer(self, params: Note) -> Note:
            return Note(params.text.upper())

        @rpc_notification("plain/note")
        def note(self, params: Note) -> None:
            self.notes.append(params)

    endpoint = Plain()
    connected.right.attach_endpoint(endpoint)

    assert await asyncio.wait_for(connected.left.send_request("plain/answer", {"text": "x"}), 2) == {"text": "X"}
    await connected.left.send_notification("plain/note", {"text": "y"})
    await _wait_until(lambda: bool(endpoint.notes))
    assert endpoint.notes == [Note("y")]


async def test_marked_static_and_class_methods_answer(connected: ConnectedPeers) -> None:
    class WithoutSelf(JsonRpcEndpoint):
        @staticmethod
        @rpc_request("without/static")
        async def from_static(params: Note) -> Note:
            return Note(f"static {params.text}")

        @classmethod
        @rpc_request("without/class")
        async def from_class(cls, params: Note) -> Note:
            return Note(f"{cls.__name__} {params.text}")

    connected.right.attach_endpoint(WithoutSelf())

    assert await asyncio.wait_for(connected.left.send_request("without/static", {"text": "x"}), 2) == {
        "text": "static x"
    }
    assert await asyncio.wait_for(connected.left.send_request("without/class", {"text": "x"}), 2) == {
        "text": "WithoutSelf x"
    }


async def test_attaching_runs_no_property_of_the_endpoint(connected: ConnectedPeers) -> None:
    class WithProperty(WorkingCalculator):
        ran = False

        @property
        def expensive(self) -> int:
            type(self).ran = True
            return 1

    connected.right.attach_endpoint(WithProperty())

    assert WithProperty.ran is False


# --- several endpoints on the receiving side ----------------------------------


async def test_two_endpoints_on_one_peer(connected: ConnectedPeers) -> None:
    calculator = WorkingCalculator()
    console = WorkingConsole()
    connected.right.attach_endpoint(calculator)
    connected.right.attach_endpoint(console)

    assert await asyncio.wait_for(connected.left.send_request("calc/add", {"a": 1, "b": 2}), 2) == {"sum": 3}
    await connected.left.send_notification("console/print", {"text": "hello"})
    await _wait_until(lambda: bool(console.printed))

    assert console.printed == [Note("hello")]


async def test_one_class_implements_two_definitions(connected: ConnectedPeers) -> None:
    class Both(Calculator, Console):
        def __init__(self) -> None:
            self.printed: list[Any] = []

        async def add(self, params: AddParams) -> AddResult:
            return AddResult(params.a + params.b)

        async def note(self, params: Note) -> None:
            pass

        async def print(self, params: Note) -> None:
            self.printed.append(params)

    both = Both()
    connected.right.attach_endpoint(both)

    assert await asyncio.wait_for(connected.left.send_request("calc/add", {"a": 1, "b": 2}), 2) == {"sum": 3}
    await connected.left.send_notification("console/print", {"text": "hello"})
    await _wait_until(lambda: bool(both.printed))

    assert both.printed == [Note("hello")]


async def test_one_method_answers_two_definitions_with_the_same_python_name(connected: ConnectedPeers) -> None:
    class First(JsonRpcEndpoint):
        @rpc_notification("first/log")
        @abstractmethod
        async def log(self, params: Note) -> None: ...

    class Second(JsonRpcEndpoint):
        @rpc_notification("second/log")
        @abstractmethod
        async def log(self, params: Note) -> None: ...

    class Both(First, Second):
        def __init__(self) -> None:
            self.logged: list[Any] = []

        async def log(self, params: Note) -> None:
            self.logged.append(params)

    both = Both()
    connected.right.attach_endpoint(both)

    await connected.left.remote(First).log(Note("a"))
    await connected.left.remote(Second).log(Note("b"))
    await _wait_until(lambda: len(both.logged) == 2)

    assert both.logged == [Note("a"), Note("b")]


async def test_remote_of_a_method_with_two_marks_sends_the_nearest(connected: ConnectedPeers) -> None:
    class First(JsonRpcEndpoint):
        @rpc_request("first/ask")
        @abstractmethod
        async def ask(self, params: Note) -> Note: ...

    class Second(JsonRpcEndpoint):
        @rpc_request("second/ask")
        @abstractmethod
        async def ask(self, params: Note) -> Note: ...

    class Both(First, Second):
        async def ask(self, params: Note) -> Note:
            return params

    async def first(params: Any) -> Any:
        return {"text": "first"}

    connected.right.register_request_handler("first/ask", first)

    assert await asyncio.wait_for(connected.left.remote(Both).ask(Note("x")), 2) == Note("first")


async def test_two_handlers_for_one_method_raise(connected: ConnectedPeers) -> None:
    connected.right.attach_endpoint(WorkingCalculator())

    with pytest.raises(JsonRpcMethodAlreadyRegisteredError, match="calc/add"):
        connected.right.attach_endpoint(WorkingCalculator())


# --- calling a definition -----------------------------------------------------


async def test_request_through_remote_sends_its_name_and_params_and_converts_the_result(
    connected: ConnectedPeers,
) -> None:
    seen: list[Any] = []

    async def add(params: Any) -> Any:
        seen.append(params)
        return {"sum": 3}

    connected.right.register_request_handler("calc/add", add)

    result = await asyncio.wait_for(connected.left.remote(Calculator).add(AddParams(1, 2)), 2)

    assert result == AddResult(3)
    assert seen == [{"a": 1, "b": 2}]


async def test_params_as_a_keyword_send_the_same_message(connected: ConnectedPeers) -> None:
    class OtherName(JsonRpcEndpoint):
        @rpc_request("other/answer")
        @abstractmethod
        async def answer(self, note: Note) -> Note: ...

    seen: list[Any] = []

    async def answer(params: Any) -> Any:
        seen.append(params)
        return params

    connected.right.register_request_handler("other/answer", answer)
    remote = connected.left.remote(OtherName)

    assert await asyncio.wait_for(remote.answer(Note("positional")), 2) == Note("positional")
    assert await asyncio.wait_for(remote.answer(note=Note("keyword")), 2) == Note("keyword")
    assert seen == [{"text": "positional"}, {"text": "keyword"}]


async def test_request_without_a_return_annotation_returns_the_result_as_it_arrived(connected: ConnectedPeers) -> None:
    class NoReturn(JsonRpcEndpoint):
        @rpc_request("raw/answer")
        @abstractmethod
        async def answer(self, params: Note): ...  # type: ignore[no-untyped-def]

    async def answer(params: Any) -> Any:
        return {"anything": [1, 2]}

    connected.right.register_request_handler("raw/answer", answer)

    assert await asyncio.wait_for(connected.left.remote(NoReturn).answer(Note("x")), 2) == {"anything": [1, 2]}


class _CollectingWriter:
    """A stream writer that keeps what the peer writes."""

    def __init__(self) -> None:
        self.written = bytearray()

    def write(self, data: bytes | memoryview) -> None:
        self.written += data

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass

    def message(self) -> Any:
        return json.loads(bytes(self.written).partition(b"\r\n\r\n")[2])


async def test_notification_through_remote_has_no_id_and_returns_none() -> None:
    writer = _CollectingWriter()
    peer = JsonRpcPeer(asyncio.StreamReader(), cast("asyncio.StreamWriter", writer))

    result = await peer.remote(Calculator).note(Note("hello"))  # type: ignore[func-returns-value]

    assert result is None
    assert writer.message() == {"jsonrpc": "2.0", "method": "calc/note", "params": {"text": "hello"}}


async def test_error_response_reaches_the_caller_with_its_fields(connected: ConnectedPeers) -> None:
    async def add(params: Any) -> Any:
        raise JsonRpcResponseError(-32099, "my own", {"a": 1})

    connected.right.register_request_handler("calc/add", add)

    with pytest.raises(JsonRpcResponseError) as error:
        await asyncio.wait_for(connected.left.remote(Calculator).add(AddParams(1, 2)), 2)

    assert (error.value.code, error.value.message, error.value.data) == (-32099, "my own", {"a": 1})


async def test_closed_connection_reaches_the_caller(connected: ConnectedPeers) -> None:
    await connected.left.stop()
    remote = connected.left.remote(Calculator)

    with pytest.raises(JsonRpcConnectionClosedError):
        await asyncio.wait_for(remote.add(AddParams(1, 2)), 2)
    with pytest.raises(JsonRpcConnectionClosedError):
        await remote.note(Note("hello"))


async def test_result_that_does_not_fit_raises_and_the_connection_stays_open(connected: ConnectedPeers) -> None:
    answers = ["not a result", {"sum": 3}]

    async def add(params: Any) -> Any:
        return answers.pop(0)

    connected.right.register_request_handler("calc/add", add)
    remote = connected.left.remote(Calculator)

    with pytest.raises(TypeError, match="not a result"):
        await asyncio.wait_for(remote.add(AddParams(1, 2)), 2)

    assert await asyncio.wait_for(remote.add(AddParams(1, 2)), 2) == AddResult(3)


async def test_object_from_remote_is_an_instance_of_the_definition(connected: ConnectedPeers) -> None:
    remote = connected.left.remote(Calculator)

    assert isinstance(remote, Calculator)
    assert remote.rpc_peer is connected.left


async def test_remote_gives_one_object_for_each_definition_on_each_peer(connected: ConnectedPeers) -> None:
    first = connected.left.remote(Calculator)
    other_definition: Any = connected.left.remote(Console)

    assert connected.left.remote(Calculator) is first
    assert other_definition is not first

    other_peer = connected.right.remote(Calculator)
    assert other_peer is not first
    assert other_peer.rpc_peer is connected.right


async def test_default_implementation_is_sent_and_does_not_run(connected: ConnectedPeers) -> None:
    async def answer(params: Any) -> Any:
        return {"text": "from the other side"}

    connected.right.register_request_handler("default/answer", answer)

    assert await asyncio.wait_for(connected.left.remote(WithDefault).answer(Note("x")), 2) == Note(
        "from the other side"
    )


async def test_remote_refuses_a_class_that_is_not_an_endpoint(connected: ConnectedPeers) -> None:
    class NotAnEndpoint:
        pass

    with pytest.raises(TypeError, match="NotAnEndpoint"):
        connected.left.remote(NotAnEndpoint)  # type: ignore[type-var]


async def test_remote_refuses_a_method_with_two_parameters(connected: ConnectedPeers) -> None:
    class TwoParameters(JsonRpcEndpoint):
        @rpc_request("two/parameters")
        @abstractmethod
        async def two(self, peer: JsonRpcPeer, params: Note) -> Note: ...

    with pytest.raises(TypeError, match=r"TwoParameters\.two"):
        connected.left.remote(TwoParameters)


async def test_remote_refuses_a_plain_method(connected: ConnectedPeers) -> None:
    class PlainMethod(JsonRpcEndpoint):
        @rpc_request("plain/answer")
        def answer(self, params: Note) -> Note:
            return params

    with pytest.raises(TypeError, match=r"PlainMethod\.answer"):
        connected.left.remote(PlainMethod)


# --- an endpoint calls the other side -----------------------------------------


async def test_attached_endpoint_calls_through_its_remote(connected: ConnectedPeers) -> None:
    console = WorkingConsole()
    connected.left.attach_endpoint(console)
    connected.right.attach_endpoint(calculator := WorkingCalculator())

    await calculator.remote(Console).print(Note("hello"))
    await _wait_until(lambda: bool(console.printed))

    assert console.printed == [Note("hello")]


@pytest.mark.parametrize("set_to_none", [False, True], ids=["never attached", "rpc_peer set to None"])
async def test_endpoint_without_a_peer_raises(connected: ConnectedPeers, set_to_none: bool) -> None:
    calculator = WorkingCalculator()
    if set_to_none:
        connected.right.attach_endpoint(calculator)
        calculator.rpc_peer = None

    with pytest.raises(RuntimeError, match="WorkingCalculator"):
        calculator.remote(Console)


# --- several definitions on one peer ------------------------------------------


async def test_two_definitions_with_the_same_python_name_send_their_own_names(connected: ConnectedPeers) -> None:
    class First(JsonRpcEndpoint):
        @rpc_notification("first/log")
        @abstractmethod
        async def log(self, params: Note) -> None: ...

    class Second(JsonRpcEndpoint):
        @rpc_notification("second/log")
        @abstractmethod
        async def log(self, params: Note) -> None: ...

    seen: list[tuple[str, Any]] = []

    async def first(params: Any) -> None:
        seen.append(("first", params))

    async def second(params: Any) -> None:
        seen.append(("second", params))

    connected.right.register_notification_handler("first/log", first)
    connected.right.register_notification_handler("second/log", second)

    await connected.left.remote(First).log(Note("a"))
    await connected.left.remote(Second).log(Note("b"))
    await _wait_until(lambda: len(seen) == 2)

    assert seen == [("first", {"text": "a"}), ("second", {"text": "b"})]


class _Asker(JsonRpcEndpoint):
    @rpc_request("asker/ask")
    @abstractmethod
    async def ask(self, params: Note) -> Note: ...


async def test_both_directions_on_one_connection(connected: ConnectedPeers) -> None:
    class Asks(WorkingCalculator):
        async def add(self, params: AddParams) -> AddResult:
            # A request back to the other side from inside a handler, and a notification.
            answer = await self.remote(_Asker).ask(Note("how much?"))
            await self.remote(Console).print(Note(answer.text))
            return AddResult(params.a + params.b + int(answer.text))

    class Answers(_Asker, WorkingConsole):
        async def ask(self, params: Note) -> Note:
            return Note("10")

    answers = Answers()
    connected.left.attach_endpoint(answers)
    connected.right.attach_endpoint(Asks())

    result = await asyncio.wait_for(connected.left.remote(Calculator).add(AddParams(1, 2)), 2)
    await _wait_until(lambda: bool(answers.printed))

    assert result == AddResult(13)
    assert answers.printed == [Note("10")]


async def test_definition_that_the_peer_also_implements_goes_to_the_other_side(connected: ConnectedPeers) -> None:
    here = WorkingCalculator()
    there = WorkingCalculator()
    connected.left.attach_endpoint(here)
    connected.right.attach_endpoint(there)

    assert await asyncio.wait_for(connected.left.remote(Calculator).add(AddParams(1, 2)), 2) == AddResult(3)

    assert here.added == []
    assert there.added == [AddParams(1, 2)]


# --- the example --------------------------------------------------------------


async def test_class_based_example_answers_its_definition(
    connected: ConnectedPeers, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.syspath_prepend(Path(__file__).parent.parent.parent / "packages" / "jsonrpcpeer" / "examples")
    api = importlib.import_module("class_based_api")
    server = importlib.import_module("class_based_server")
    client = importlib.import_module("class_based_client")
    connected.right.attach_endpoint(server.WorkingCalculator())
    connected.left.attach_endpoint(client.PrintingLog())

    result = await asyncio.wait_for(connected.left.remote(api.Calculator).add(api.AddParams(a=10.0, b=20.0)), 2)
    await _wait_until(lambda: "Adding" in capsys.readouterr().out)

    assert result == api.AddResult(result=30.0)


# --- what a type checker sees ---------------------------------------------------


async def _calls_for_the_type_checker(peer: JsonRpcPeer, endpoint: JsonRpcEndpoint) -> None:
    """Checked by mypy and run by no test: `warn_unused_ignores` fails the gate if an expected error goes away."""
    # An abstract definition, and the type of the result.
    remote = peer.remote(Calculator)
    assert_type(remote, Calculator)
    assert_type(await remote.add(AddParams(1, 2)), AddResult)
    assert_type(endpoint.remote(Console), Console)

    # Params of the wrong type, and a method that the definition does not have.
    await remote.add(Note("wrong"))  # type: ignore[arg-type]
    await remote.subtract(AddParams(1, 2))  # type: ignore[attr-defined]

    # A plain method as an override of an `async def`.
    class PlainOverride(WorkingCalculator):
        def add(self, params: AddParams) -> AddResult:  # type: ignore[override]
            return AddResult(0)
