# Proposal

## Why

Both sides of a connection spell out every method by hand, and nothing ties the parts of a call together.

- **Calls are long and unchecked.** A call in the client reads `self.rpc_peer.send_request_typed(InitializeResult, INITIALIZE_REQUEST, InitializeParams(...))`. `params` is `Any`, and the result type is whatever the caller names, so `ShutdownParams()` in that call passes `mypy` and `pyright`, and so does a wrong result type.
- **The same facts are written twice.** The handler on the other side repeats the method name and the types.
- **The client needs wrappers for this.** `_ClientEndpoint` has seven methods that do little more than send one message, and eight checks of `if self.rpc_peer is None: raise RuntimeError(...)`.
- **A plain function as a handler fails late.** It runs, and then the request gets `-32603 object dict can't be used in 'await' expression`, and a notification is reported as failed.
- **`jsonrpcpeer` should work for larger protocols too.** The package is meant to be reused, for example in RobotCode, where this repetition grows with every method.

`JsonRpcEndpoint` in `peer.py` marks this idea so far: it only collects handlers, and nothing uses it.

## What Changes

An endpoint definition states an interface once. One side implements it, the other side calls it:

```python
# Defined once
class ServerEndpoint(JsonRpcEndpoint):
    @rpc_request(INITIALIZE_REQUEST)
    @abstractmethod
    async def initialize(self, params: InitializeParams) -> InitializeResult: ...


# One side implements it
class RobotServerEndpoint(ServerEndpoint):
    async def initialize(self, params: InitializeParams) -> InitializeResult:
        return InitializeResult(...)


peer.attach_endpoint(RobotServerEndpoint())

# The other side calls it
result = await peer.remote(ServerEndpoint).initialize(InitializeParams(...))
```

- **Definition:** a subclass of `JsonRpcEndpoint`, an abstract class, whose methods carry `rpc_request` or `rpc_notification` and `abstractmethod`. It names the method on the wire and the types of its params and its result.
- **Implementing:** a subclass of a definition overrides its methods, written as handlers are today, without a mark of their own. `attach_endpoint` finds the mark in the definition. If a method is missing, creating the object raises a `TypeError` that names it, and `mypy` and `pyright` report it too.
- **Calling:** `peer.remote(ServerEndpoint)` gives an object whose methods send: a request waits for its result and converts it to the declared type, and a notification is sent without waiting. Inside an endpoint, `self.remote(ClientEndpoint)` does the same and raises a `RuntimeError` if the endpoint is not attached. For `mypy` and `pyright`, the object is a `ServerEndpoint`, so wrong params and unknown methods are found.
- **Several endpoints on one peer:** the definition selects the interface, as in `peer.remote(A)` and `peer.remote(B)`. On the receiving side, `attach_endpoint` can be called several times, as today, or one class implements several definitions. Two handlers for the same method still raise `JsonRpcMethodAlreadyRegisteredError`.
- **Plain functions as handlers:** a handler can be a plain function as well as an async one. It runs on the event loop, as an async handler without an `await` does. A definition stays `async def`, because a call over the wire always waits, and type checkers report a plain method as an override of it.
- **The Robot protocol:** `robot_jsonrpcremote_protocol` gets the definitions `ServerEndpoint` and `ClientEndpoint`, so that package now depends on `jsonrpcpeer`. The client, the server and the example server use them. The wrappers in `_ClientEndpoint` go away; what holds logic stays there, `report_log_level` and `graceful_shutdown`.
- **Replaced:** the old `JsonRpcEndpoint` that collects handlers, and `JsonRpcEndpointProtocol`. `attach_endpoint` takes a `JsonRpcEndpoint`.
- **Unchanged:** nothing changes on the wire. `rpc_request` and `rpc_notification` also work on a class without a separate definition. `send_request`, `send_request_typed`, `send_notification` and `register_request_handler` and `register_notification_handler` stay for code without definitions, and the tests that check messages on the wire keep using them.

Out of scope, to keep this simple:

- Methods without params, or calls with several arguments. As with handlers today, a method takes one params object.
- A shortcut in `jsonrpcpeer` such as an attribute `self.server` for `self.remote(ServerEndpoint)`. An endpoint that wants one writes a property, as the client does.
- Handlers in threads and cancelling a request. Both can follow later without changing the definitions.
- Changes to RobotCode and to the minimum Python version of this project.

## Capabilities

### New Capabilities

- `protocol`: the definitions of both sides of the Robot protocol in `robot_jsonrpcremote_protocol`, with the method names and the types of each message.

### Modified Capabilities

- `jsonrpc-peer`: endpoint definitions, implementing them through `attach_endpoint`, calling them through `remote`, several endpoints on one peer, and plain functions as handlers.

`client` and `server` have no delta: they use the definitions, but they behave as before. Their requirements and both test suites cover that.

## Impact

- **Peer:** `packages/jsonrpcpeer/src/jsonrpcpeer/peer.py` and its exports in `__init__.py`. `JsonRpcEndpointProtocol` is no longer exported.
- **Protocol:** `packages/protocol/src/robot_jsonrpcremote_protocol/__init__.py`. `packages/protocol/pyproject.toml` gets the dependency on `jsonrpcpeer`, and `uv.lock` changes with it.
- **Client:** `src/JsonRpcRemote/__init__.py`.
- **Server:** `packages/server/src/robot_jsonrpcremote_server/_endpoint.py`.
- **Examples:** `examples/simple-robot-jsonrpcserver` and `packages/jsonrpcpeer/examples/class_based_*`.
- **Documentation:** `packages/jsonrpcpeer/README.md`, `packages/protocol/README.md`, `examples/simple-robot-jsonrpcserver/README.md`, the root `README.md`, the pages `index.mdx`, `reference/protocol.mdx` and `roadmap.mdx`, and `CONTRIBUTING.md`.
- **Tests:** the new files `tests/test_typed_endpoints.py` and `tests/connected_peers.py`, and `tests/test_peer.py`, `tests/test_protocol.py`, `tests/test_endpoint.py`, `tests/test_client_logging.py`, `tests/test_client_session.py`, `tests/test_example_server.py`. Nothing can be observed from Robot Framework, so the Robot suites run as a regression check and get no new test.
