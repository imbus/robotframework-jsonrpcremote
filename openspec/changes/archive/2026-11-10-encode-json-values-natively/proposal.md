# Proposal

## Why

Keyword arguments and return values go over the wire through `value_to_jsonable` of `jsonrpcpeer.json_helpers`. It sends only `None`, strings, numbers and booleans as JSON and pickles everything else, so even `[1, 2]` or `{"a": 1}` travel as `{"__pickled__": "8004..."}`. Both sides already accept nested JSON values, but a server in another language gets a pickle for every list and dict, although the protocol is meant to be language-agnostic: the example server `examples/simple-robot-jsonrpcserver` logs `{'__pickled__': '80049509...'}` for `[1, 2]`. Neither side can say that it reads no pickles, so a server in another language cannot refuse them, and a suite cannot be held to the values that such a server reads. A value of a class, such as a dataclass, can only travel as a pickle, although the keyword's signature names its class and a server in another language could use the same JSON form. In addition, `NaN` and infinite floats are written as `NaN` and `Infinity`, which JSON does not allow, so a peer that reads JSON strictly, such as `vscode-jsonrpc`, cannot read the message.

Pickles stay: between Python peers, they carry values that JSON cannot hold, in a standard format.

Found in the project review of 2026-10-27 (item JSON-2).

## What Changes

- **JSON where possible:** a list, a dict with string keys, and Robot Framework's `DotDict`, which `&{dict}` variables and `Create Dictionary` give, travel as plain JSON if every item in them is a JSON value, recursively. A `DotDict` arrives as a plain dict, as with Robot Framework's Remote library.
- **Pickles by agreement:** in `initialize`, the client and the server each state the highest pickle protocol that they read, in a new field `pickle_protocol` of `ClientCapabilities` and `ServerCapabilities`; a side without it reads no pickles. When both sides read pickles, every value that is not plain JSON and whose place does not declare its type is pickled as a whole, with the lower of the two protocols, as today. Subclasses of the JSON types, such as an `IntEnum`, are pickled too, so they keep their type; today an `IntEnum` arrives as a plain `int`. A side that reads no pickles fails the call instead of unpickling one that arrives anyway.
- **Typed values:** instances of dataclasses, enums and named tuples, values of standard types such as `datetime`, `Decimal`, `bytes`, `UUID` and `Path`, and built-in values without a JSON form, such as tuples, sets, dicts with keys other than strings and `NaN`, travel as typed JSON, in the forms that the protocol spec gives:
  - Client and server have the same classes installed, in the same modules. The Python class defines the JSON form, so no other description of it travels. A server in another language names the Python class and writes its JSON form.
  - The library definition names classes with their module, such as `mytypes.Point`, in the types of the arguments, and gets the return type of each keyword.
  - Where the signature declares the type, the value travels in its form, also when both sides read pickles. Where it does not, and no pickles are agreed, the value names its type in the key `__type__`, as in `{"__type__": "mytypes.Point", "x": 1, "y": 2}`.
  - The receiver imports the class and builds the value from its form, also inside lists and dicts, for these kinds only.
  - The server turns arguments into the types of the keyword's signature, dataclasses included. The client gives Robot Framework the classes of the declared types, so that Robot converts arguments on the client already and Libdoc shows the classes.
- **Unambiguous markers:** a dict that holds the key `__pickled__` or `__type__` is pickled, or fails without pickles, so an object with one of these keys on the wire is always a pickle or a typed value.
- **Failures:** a value that may not travel under the agreement fails the call with a `TypeError`, and a typed value that does not fit its class, or whose class is not installed, with a `ValueError` worded as Robot Framework words a failed conversion. The specs and the design give the cases and the messages.
- **Turning pickles off:** pickles stay on by default. On the server, `--no-pickles` turns them off and `--pickles` on, and the environment variable `ROBOT_JSONRPC_PICKLES` sets the default with the truth values that Robot Framework knows for booleans. On the client, the library option `rpc_pickles=False` turns them off.
- **The value format in the protocol package:** the encoding and decoding of values moves from `jsonrpcpeer.json_helpers` to the protocol package `robot_jsonrpcremote_protocol`, which client and server share. `jsonrpcpeer` keeps only its general JSON helpers, such as `from_dict`, `as_dict` and `as_json`, as in RobotCode, from which they come.
- **Valid JSON only:** the peer writes no message that holds `NaN` or an infinite float; such a message fails as any other message that cannot be written as JSON does today. The peer still reads such values.
- **Example server:** the hand-written example server states no pickle protocol, as a server in another language would, and gets a keyword with an argument and a return value of a dataclass from a module of its package.
- **Tests:** unit tests of the value format for each kind of value, with and without pickles, of the agreement against the fake server, and of the peer for `NaN`; Robot tests of plain JSON, pickles and typed values with pickles on and off on either side, of the failures, and of the typed keyword of the example server.
- **Docs:** the page Protocol describes the value format, the class names and return types in the library definition, and the new capability fields; the references of the server and the library describe the options, and the reference of the library says that the classes of typed values must be installed on the client; the page Status and roadmap lists plain JSON, typed values and the agreement on pickles as available.

Assumptions recorded for review:

- A pickle is only ever a whole value, since a pickle is only unpacked at the top level; pickles inside JSON are left to a later change (SEC-1). Typed values may sit inside lists and dicts.
- On Python 3.12 to 3.14, every side reads protocol 5, so the protocol in the agreement changes nothing today; it prepares for a later protocol.
- Between Python peers with pickles on, as by default, values whose place declares no type keep travelling as pickles; there, typed JSON applies when one side turns pickles off and with servers in other languages.
- Users keep the classes and their versions in step on both sides, as servers run in environments that they trust. A class that differs, or a return value that does not fit its declared type, fails the call with a message that says why.

Out of scope: Pydantic models and attrs classes as typed values; objects that hold a live resource, such as a WebDriver or an open connection, which would need handles that stay on the server.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `json-conversion`: the requirement on `value_to_jsonable` and `jsonable_to_value` is removed, since the value format moves to the protocol package; the requirement on `as_json` gets a scenario: it fails for `NaN` and infinite floats.
- `protocol`: adds requirements on the value format: lists, dicts and `DotDict`s of JSON values as plain JSON; pickles by the agreement, with the lower protocol; typed values in their forms, with `__type__` where the type is not declared, built back only for the supported kinds; the markers; and the failures.
- `jsonrpc-peer`: the requirement on a response that cannot be written gets a scenario for a result that holds `NaN`.
- `client`: adds requirements on stating its pickle protocol, on sending and unpickling pickles only by the agreement, and on the option `rpc_pickles`; on the class names and return types in the library definition, on typed values in arguments and return values, on giving Robot Framework the declared classes, and on the failures.
- `server`: adds the same requirements on pickles for the server, with the options `--pickles` and `--no-pickles` and the environment variable `ROBOT_JSONRPC_PICKLES`; on naming classes with their modules and stating return types in the library definition, on typed values, and on turning arguments into the types of the signature.

## Impact

- **Code:** the value format in a new module of `packages/protocol/src/robot_jsonrpcremote_protocol/`, which walks values by their declared types itself; `ClientCapabilities`, `ServerCapabilities` and `KeywordDefinition` in its `__init__.py`; `packages/jsonrpcpeer/src/jsonrpcpeer/json_helpers.py` loses `value_to_jsonable`, `jsonable_to_value` and the pickle helpers, and its `as_json` writes no `NaN`; the client in `src/JsonRpcRemote/__init__.py`; the server in `packages/server/src/robot_jsonrpcremote_server/` (`_endpoint.py`, `_runner.py`, `__main__.py`); the example server in `examples/simple-robot-jsonrpcserver`.
- **Wire format:** lists and dicts of JSON values become plain JSON; values of the supported kinds become typed JSON where the signature declares their type, and without pickles also elsewhere, with `__type__`; `ClientCapabilities` and `ServerCapabilities` get the field `pickle_protocol`; the library definition names classes with their module and gets return types.
- **Docs:** `docs/src/content/docs/reference/protocol.mdx`, `docs/src/content/docs/reference/library.mdx`, `docs/src/content/docs/reference/server.mdx` and `docs/src/content/docs/roadmap.mdx`, and the README of the example server.
