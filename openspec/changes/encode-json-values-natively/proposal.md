# Proposal

## Why

Keyword arguments, return values and argument defaults go over the wire through `value_to_jsonable`. It sends only `str`, `int`, `float`, `bool` and `None` as JSON and pickles everything else, so even `[1, 2]` or `{"a": 1}` travel as `{"__pickled__": "8004..."}`. That has four consequences:

- **Not language-agnostic:** a server or client written in another language cannot use lists or dicts, although the README promises a language-agnostic protocol. The example server in `examples/simple-robot-jsonrpcserver` receives `{'__pickled__': '80049509...'}` for `[1, 2]`.
- **More pickles than needed:** every list and every dict is a pickle and adds to the attack surface of unpickling, which can execute code.
- **Ambiguous marker:** a plain dict that happens to contain the key `__pickled__` is unpickled on the receiving side.
- **Invalid JSON:** `NaN` and infinite floats are written as `NaN` and `Infinity`, which JSON does not allow.

Found in the project review of 2026-10-27 (item JSON-2).

## What Changes

- **JSON where possible:** a list, or a dict with string keys, is sent as plain JSON if all its items are JSON values, recursively.
- **Pickle for the rest:** everything else is pickled as a whole, as today: tuples, sets, dicts with other keys, any other object, and lists or dicts that contain such a value anywhere inside. A dict that contains the key `__pickled__` is pickled too, so the marker stays unambiguous.
- **Floats:** `NaN` and infinite floats are pickled instead of being written as invalid JSON.
- **Tests:** round trips for every kind of value; the example server receives a list and a dict as plain JSON.
- **Docs:** the protocol pages of the documentation site state which values travel as JSON and which as pickles, with a runnable example; the claim of a language-agnostic protocol now holds for lists and dicts too.

Assumptions recorded for review:

- Compatible in both directions. A receiver from before this change gets plain JSON and passes it through `jsonable_to_value` unchanged; it never sees a pickle nested inside JSON, because a value that needs pickling is pickled as a whole. Pickles from an older sender are decoded as before.
- Types are preserved. Only values of exactly the JSON types travel as JSON; subclasses, for example an `IntEnum`, a `str` subclass or an `OrderedDict`, are pickled, so they arrive with their type. Today an `IntEnum` arrives as a plain `int`.

## Capabilities

### New Capabilities

- `value-encoding`: how keyword arguments, return values and argument defaults are encoded in protocol messages, and which values travel as JSON and which as pickles.

### Modified Capabilities

_None._

## Impact

- **Code:** `packages/jsonrpcpeer/src/jsonrpcpeer/json_helpers.py` (`value_to_jsonable`).
- **Wire format:** lists and dicts of JSON values become plain JSON; see the compatibility assumption.
- **Security:** fewer pickles on the wire. Pickle itself stays; hardening it is not part of this series.
- **Docs:** the protocol pages of the documentation site (value encoding and the note on the implementation status) and the overview in `README.md` (language-agnostic protocol).
- **Order:** after `fix-json-helpers` and `add-robot-integration-tests`, whose tests guard the round trips.
