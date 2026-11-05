# Design

## Context

See `proposal.md` for the motivation and the delta specs for the behavior. These facts of the current code shape the approach:

- `rpc_request` and `rpc_notification` only set an attribute on the function. `attach_endpoint` goes through `dir(endpoint)`, reads every attribute and looks for that mark. An override in a subclass has no mark, so it would not be found.
- `_get_and_check_handler_param_type` reads the annotations of the handler it gets, which takes `(params)` or `(peer, params)`.
- `_call_handler` always awaits what a handler returns. So a plain function runs and then fails with `-32603 object dict can't be used in 'await' expression`, while `THandlerCallable` only describes async functions.
- `send_request_typed` takes the result type, the name and `params: Any`. It raises what a call can raise, so the new calls need no error handling of their own.
- `JsonRpcEndpoint` collects handlers and nothing uses it. `JsonRpcEndpointProtocol` only says that an endpoint has `rpc_peer`.
- `packages/protocol` has no dependency. The client, the server and the example server depend on it and on `jsonrpcpeer`.
- `RobotServerEndpoint.log()` checks `if self.rpc_peer:` on purpose: after `cleanup()`, a late log message does nothing.

The approach was tried out as a prototype on a copy of the repository, with the client, the server and the example server moved over. All unit tests and all 167 Robot tests stay green, and `mypy` is clean. The client gets 72 lines shorter, the server and the example server 18 lines each; the peer grows by about 45 lines and the protocol package by about 45.

## Goals / Non-Goals

**Goals:**

- One definition states the name and the types of a method for both sides, and type checkers hold both sides to it.
- The peer stays generic: it knows nothing of the Robot protocol.
- Nothing changes on the wire.

**Non-Goals:**

- Comparing the signature of an override with its definition at runtime. Type checkers do that.
- Checking the type of the params at runtime when sending. `send_request_typed` takes anything that can be written as JSON, and that stays.
- A method for `robot/trace`. The message is defined, but nothing sends it.
- Handlers in threads. They can come later as a decorator around the handler, with no change to the peer and to the definitions: the peer sees an async handler, and a type checker accepts `@threaded def` as an override of an `async def`.
- Cancelling a request. It can come later in the peer, with no change to the definitions, because an async handler gets the `CancelledError` of its task and needs no token.

## Decisions

### 1. A definition is an abstract class

A definition derives from `JsonRpcEndpoint`, an `abc.ABC`, and its methods carry the mark and `abstractmethod`:

```python
class ServerEndpoint(JsonRpcEndpoint):
    @rpc_request(INITIALIZE_REQUEST)
    @abstractmethod
    async def initialize(self, params: InitializeParams) -> InitializeResult: ...
```

Python then raises a `TypeError` that names a missing method when the object is created, with no code of ours, and `mypy` and `pyright` report it too. A method without `abstractmethod` can have a default implementation.

Alternatives, all tried with `mypy` and `pyright`:

- `typing.Protocol`: one line less for each method, and the checkers report a missing method as well. But each definition has to name `Protocol` again, and at runtime the object is created and the missing method answers with `None` unless `attach_endpoint` checks for that itself.
- A plain class with `...` as the body: `mypy` reports `empty-body` on each method, and nobody reports a missing method.
- A plain class with `raise NotImplementedError`: nobody reports a missing method until it is called.

### 2. `remote` takes a `TypeForm`, not a `type`

```python
def remote(self, definition: TypeForm[E]) -> E: ...
```

With `type[E]`, `mypy` refuses an abstract class and a protocol at the call: `Only concrete class can be given where "type[...]" is expected [type-abstract]`. Every caller would have to switch off that error. `TypeForm[E]` has no such rule, and `json_helpers.from_dict` already uses it, so the package already depends on it through `typing_extensions`.

Tried on a project that has the packages installed as wheels, in strict mode and without a setting of its own, with the current `mypy` 2.4.1 and with `pyright` 1.1.414. Both accept the abstract definition, give the definition as the type of the result, and report wrong params and unknown methods.

`Callable[..., E]` passes too, but it says something else: any function that returns an `E` would be accepted.

### 3. The call is named `remote`, on the peer and on the endpoint

`peer.remote(ServerEndpoint)` from outside, and `self.remote(ClientEndpoint)` inside an endpoint. The name says that the call goes to the other side, which matters when the same peer also implements that definition.

`rpc_peer` stays `JsonRpcPeer | None`, as a class attribute of `JsonRpcEndpoint` with the default `None`, so the checks of the server keep working. `JsonRpcEndpoint.remote` raises the `RuntimeError` that each wrapper in `_ClientEndpoint` raises today.

Alternative: `peer(ServerEndpoint)` as in the first sketch of this idea. It is shorter, but a callable peer is harder to find in the code. Written as `self.rpc_peer(ClientEndpoint)` inside an endpoint it does not pass `mypy` while `rpc_peer` can be `None`, so `rpc_peer` would have to become a property that raises, and `cleanup()` and `if self.rpc_peer:` in the server would need another way.

### 4. The object from `remote` is an instance of a generated subclass

`remote` builds one subclass of the definition for each definition, with `types.new_class` and `functools.cache`, whose marked methods send. It creates a new object of that class for each call of `remote`, with `object.__new__`, so an `__init__` of the definition does not run. The object only holds the peer in `rpc_peer`.

- For a type checker the object is a `ServerEndpoint`, and with a subclass that is also true at runtime.
- The peer holds no reference to these objects, so they add nothing to what the garbage collector has to deal with, and the requirement on freeing an ended peer stays easy to keep.
- The name and the result type are read once, when the class is built. A definition with a marked method that does not take exactly one parameter fails there, with a `TypeError` that names it.

Alternatives: an object with `__getattr__` is not an instance of the definition, and it reads the type hints for each call or needs a cache of its own. An object cached on the peer saves very little and adds a cycle.

### 5. A sending method binds its arguments to the signature of the definition

The sending method takes `*args, **kwargs` and binds them with `inspect.signature` of the method in the definition. A type checker accepts `method(params=...)` with the name from the definition, so that has to work, whatever the parameter is called, and a wrong number of arguments raises the usual `TypeError`.

### 6. Marks are found through the class hierarchy

One helper goes through the attribute names of a class and, for each name, through its `__mro__`, and takes the nearest mark. `attach_endpoint` and `remote` both use it.

- An override without a mark gets the name from its definition. An override with a mark of its own replaces it.
- It reads `vars(cls)` instead of `getattr(endpoint, name)`, so it runs no property of the endpoint. Today attaching an endpoint runs all of them.
- A marked function stored on an instance is no longer found. Nothing does that.

### 7. The params type comes from the override, the result type from the definition

On the receiving side nothing changes: the peer reads the annotation of the method it calls. That leaves `_get_and_check_handler_param_type` untouched. An override without an annotation gets the params as they arrived, like any handler without a type, and strict `mypy` reports such an override. The form `(peer, params)` stays for handlers that want it; on an override of a definition, type checkers report it as incompatible.

Alternative: always convert to the annotation of the definition. That needs a second path through the registration for a case that type checkers already report.

### 8. The definitions live in the protocol package

`ServerEndpoint` and `ClientEndpoint` go into `robot_jsonrpcremote_protocol/__init__.py`, after the messages. The package gets the dependency `jsonrpcpeer`, with `[tool.uv.sources]` for the workspace, and `uv.lock` changes with it. `tests/test_packaging.py` already checks that the dependency is declared. `jsonrpcpeer` does not depend on the protocol package, so there is no cycle. All wheels are built together, also in `docs/examples/container/run.sh`.

Alternative: a submodule with an optional extra, so that the package itself keeps no dependency. That is more work for a case that does not exist today, the dataclasses without a peer.

### 9. What happens to the code that uses the peer

- **`_ClientEndpoint`** derives from `ClientEndpoint`. `_log_notification` becomes `log`. It keeps its state, `report_log_level` and `graceful_shutdown`, which call through `self.remote(ServerEndpoint)`. `initialize`, `initialized`, `import_library`, `run_keyword`, `finalize_library`, `shutdown` and `exit` go away.
- **`_Session`** calls through `self.client_endpoint.remote(ServerEndpoint)` and builds the params itself. The values for `robot/initialize` move to `_initialize_server`. A session without a peer still raises a `RuntimeError`.
- **`RobotServerEndpoint`** and **`SimpleRobotServerEndpoint`** derive from `ServerEndpoint` and lose their marks. `_counted` stays. `log()` keeps its check and sends through `self.rpc_peer.remote(ClientEndpoint)`.
- **`packages/jsonrpcpeer/examples/class_based_*`** share a definition in a new file `class_based_api.py`. `simple_*` and `typed_*` stay as examples of the calls without definitions.
- **Tests that check the wire** keep using `send_request_typed` and `send_notification`, so that they do not depend on the definitions they check. Test classes that use marks derive from `JsonRpcEndpoint`.

### 10. How the view of a type checker is tested

`mypy` is the gate and checks `tests/` in strict mode with `warn_unused_ignores`. So a test file can state both directions: `assert_type(await peer.remote(Def).method(params), Result)` must hold, and `# type: ignore[arg-type]` on a wrong call fails the gate if the error goes away. `pyright` is not part of the gate, so the integration checks run it once on the same file.

### 11. The new code stays readable on Python 3.10

RobotCode supports Python 3.10, and `jsonrpcpeer` is meant to be reused there later. The new code uses `TypeVar` instead of the generics syntax of Python 3.12, as the rest of `peer.py` does. The minimum version of this project stays 3.12.

### 12. A handler can be a plain function

`_call_handler` calls the handler and waits only if the result is awaitable, and `THandlerCallable` describes any function:

```python
return await result if inspect.isawaitable(result) else result
```

- It checks the result and not `inspect.iscoroutinefunction`, so that a `functools.partial` of an async function and a function that returns a coroutine keep working.
- A plain function runs on the event loop and holds up the other messages while it runs. That adds no new risk: an `async def` without an `await` does the same. A function that takes long belongs in a thread or an executor, also today.
- `vscode-jsonrpc` also takes a value or a promise from a handler, and RobotCode has more plain handlers than async ones.
- A definition stays `async def`, because a call through `remote` always waits. So a plain function only fits where no definition states the method: with `register_request_handler`, `register_notification_handler` and marks on a class without a separate definition. Over a definition, type checkers report it as an incompatible override.

Alternative: refuse a plain function at registration with a `TypeError`. That also ends the late failure, but every plain function would have to become `async def` without gaining anything.

## Risks / Trade-offs

- [A definition with a method named `remote` hides `JsonRpcEndpoint.remote`] → Rare, and the author of the definition sees it at once, because `self.remote(...)` then sends a message. The peer does not check for it.
- [`functools.cache` keeps each definition and its generated class for the life of the process] → Definitions live at module level, so this costs nothing in practice. A definition inside a test function stays until the test run ends.
- [An annotation that only exists under `TYPE_CHECKING` raises a `NameError`, at the first `remote` for that definition] → The same happens to a handler at `attach_endpoint` today, and it shows at the first call of the code.
- [One more line for each method of a definition, for `abstractmethod`] → That is the price of the runtime error for a missing method; see decision 1.
