# Design

## Context

After a reconnect, `JsonRpcRemote` logs one warning text for every library: in `_ensure_session()` of `src/JsonRpcRemote/__init__.py`, after `_check_definition()`. The client has what it needs to tell the cases apart: the scheme of its URI, and the scope of the remote library in `LibraryDefinition.scope`, which the server fills from Robot Framework's `lib.scope.name`. `_check_definition()` compares every attribute of the definition, the scope included, so a reconnect to a library with another scope fails before the warning.

How Robot Framework handles the imports of the server, checked in its source, in 7.5 and in the minimum 7.2 alike:

- `Importer.import_library()` caches every library by its name and import arguments. A `GLOBAL` library keeps its instance in the cache; for the other scopes the cached library has none, so each import creates its own.
- The server imports every library with its token as the alias, so every import is a copy of the cached library; for `GLOBAL`, the copies share the instance.
- Each import registers the listeners of its copy. `LibraryListeners.unregister()` removes only the registrations of that copy, by identity. `_robot_finalize_library()` calls `scope_manager.end_suite()`, which for `GLOBAL` unregisters the listeners of the finalized copy, without closing them.
- `Namespace.end_suite()` of the root suite calls `IMPORTER.close_global_library_listeners()`, which calls `close` of the listeners of each cached `GLOBAL` library once. In the server, the root suite ends when the server stops on SIGTERM or SIGINT. A hard kill, which `terminate()` is on Windows, ends the process without it.
- Over stdio, every session starts a server process of its own, and so does the reconnect.

Probed on 2026-11-08 with a real server and counter libraries of the three scopes, the `GLOBAL` one with a listener of its own (`ROBOT_LIBRARY_LISTENER` with `start_keyword` and `close`), in a first form of the suite of decision 3:

- Three sessions one after the other count 1, 2 and 3 with the `GLOBAL` library, and 1 each time with the `SUITE` and the `TEST` library.
- After client A ended its session, client B, which stayed connected, counts on with the same instance, and the listener sees B's call; `close` has not been called.
- On SIGTERM, with B still connected, `close` is called once; each later server process calls it once more when it stops.
- The listener sees every keyword call on the server, of every library and client, once per import of its library that is registered at that moment. Robot Framework does the same for two local imports of a `GLOBAL` library under two aliases.
- Over stdio, the call after the server process exited counts 1 again, and the warning says that the state was reset.

## Goals / Non-Goals

**Goals:**

- The warning after a reconnect says what became of the server-side state, by the scope and the transport.
- Tests pin the sharing of a `GLOBAL` library, its listener after a finalize, and the close of the listener at the stop.

**Non-Goals:**

- A change to the server: finalizing already leaves the shared instance and its listeners to the other clients, and the stop closes the listeners.
- Listener events once per call instead of once per import: that is how Robot Framework treats several imports of a `GLOBAL` library.
- Telling whether a TCP server restarted: the client cannot see it, so the warning for `GLOBAL` names both cases.
- A close of the listeners when the server is killed, as `terminate()` does on Windows.

## Decisions

### 1. The warning picks its end by the scheme and the registered scope

For a `tcp://` URI and a registered definition with the scope `GLOBAL`, the warning ends with "the remote library was imported again; its library scope is GLOBAL, so its server-side state is kept unless the server restarted". For the other scopes, and for every `stdio:` URI, it keeps "the remote library was imported again, so its server-side state was reset". The text says "library scope", so that it is not read as `rpc_scope=GLOBAL`.

The registered definition is the one Robot Framework registered the keywords for. The definition of the new session has the same scope whenever the warning is logged, since `_check_definition()` fails the call otherwise.

*Alternative considered:* the text for `GLOBAL` over stdio, too. It would be true in a sense, since the new session has a new server process, but the client started that process itself and knows that the state is gone.

### 2. The server keeps its finalize

`_robot_finalize_library()` stays as it is; the check of the finalize found no problem (see Context). The requirements on the server are pinned by tests only, each with a copy that makes it fail.

### 3. The tests of the server use a server and counter libraries of their own

`atests/global_library.robot` starts a server of its own with the three counter libraries, so that the counts do not depend on other suites. The tests that count over sessions one after the other run in order, one session per test, because a session with `rpc_scope=TEST` ends only with its test. The test of the close stops the server and starts it again; it carries the tag `posix`, as the other tests of a graceful stop do. The reconnect over TCP is tested in this suite, too, since the server of `connect_retry.robot` serves only `ConnectionLossLib`, which has the scope `TEST`.

## Risks / Trade-offs

- [A listener of a `GLOBAL` library sees a call once per client that has the library imported] → Robot Framework's behavior for several imports; the tests check that an event arrives, not how often.
- [The warning for `GLOBAL` over TCP cannot say whether the state was kept] → It names both cases; the client has no way to know.
- [The tests that count over sessions depend on their order] → They are in one suite with a server of its own, and their names say which session they are.

## Migration Plan

None.
