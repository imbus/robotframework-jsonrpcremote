# Design

## Context

After a reconnect, `JsonRpcRemote` logs one warning text for every library: in `_ensure_session()` of `src/JsonRpcRemote/__init__.py`, after `_check_definition()`. The client has what it needs to tell the cases apart: whether the new session started its server process, and the scope of the remote library in `LibraryDefinition.scope`, which the server fills from Robot Framework's `lib.scope.name`. A session that starts its server process, for a `stdio:` URI or a `pipe:` URI with a command, keeps it in its resources (`_res.process`); for `tcp://` and `pipe://<name>`, they hold none. `_check_definition()` compares every attribute of the definition, the scope included, so a reconnect to a library with another scope fails before the warning.

How Robot Framework handles the imports of the server, checked in its source, in 7.5 and in the minimum 7.2 alike:

- `Importer.import_library()` caches every library by its name and import arguments. A `GLOBAL` library keeps its instance in the cache; for the other scopes the cached library has none, so each import creates its own.
- The server imports every library with its token as the alias, so every import is a copy of the cached library; for `GLOBAL`, the copies share the instance.
- Each import registers the listeners of its copy. `LibraryListeners.unregister()` removes only the registrations of that copy, by identity. `_robot_finalize_library()` calls `scope_manager.end_suite()`, which for `GLOBAL` unregisters the listeners of the finalized copy, without closing them.
- `Namespace.end_suite()` of the root suite calls `IMPORTER.close_global_library_listeners()`, which calls `close` of the listeners of each cached `GLOBAL` library once. In the server, the root suite ends when the server stops on SIGTERM or SIGINT. A hard kill, which `terminate()` is on Windows, ends the process without it.
- With a `stdio:` or `pipe:<command>` URI, every session starts a server process of its own, and so does the reconnect. With `tcp://` and `pipe://<name>`, all sessions connect to the same server process.

Probed on 2026-11-08 with a real server and counter libraries of the three scopes, the `GLOBAL` one with a listener of its own (`ROBOT_LIBRARY_LISTENER` with `start_keyword` and `close`), in a first form of the suite of decision 3:

- Three sessions one after the other count 1, 2 and 3 with the `GLOBAL` library, and 1 each time with the `SUITE` and the `TEST` library.
- After client A ended its session, client B, which stayed connected, counts on with the same instance, and the listener sees B's call; `close` has not been called.
- On SIGTERM, with B still connected, `close` is called once; each later server process calls it once more when it stops.
- The listener sees every keyword call on the server, of every library and client, once per import of its library that is registered at that moment. Robot Framework does the same for two local imports of a `GLOBAL` library under two aliases.
- Over stdio, the call after the server process exited counts 1 again, and the warning says that the state was reset.

Probed again on 2026-11-09, after `add-pipe-transport`, with the same libraries:

- Over `pipe://<name>`, with a server started with `--pipe-server`, three sessions one after the other count 1, 2 and 3 with the `GLOBAL` library; after a restart of the server, the reconnect counts 1.
- Over `pipe:<command>`, the call after the server process exited counts 1 again.
- Both warnings say today that the state was reset.
- In the form of the suite of decision 3, with a new server for each test, run twice with `--randomize tests`: two nested runs count 1 and 2 with the `GLOBAL` library, and 1 each with the other two. After a nested run as the other client ended, the client of the test counts on with 3, and the listener sees its call; `close` has not been called. On SIGTERM, `close` is called once.

## Goals / Non-Goals

**Goals:**

- The warning after a reconnect says what became of the server-side state, by the scope and by whether the client started the server.
- Tests pin the sharing of a `GLOBAL` library, its listener after a finalize, and the close of the listener at the stop.

**Non-Goals:**

- A change to the server: finalizing already leaves the shared instance and its listeners to the other clients, and the stop closes the listeners.
- Listener events once per call instead of once per import: that is how Robot Framework treats several imports of a `GLOBAL` library.
- Telling whether a server that the client did not start restarted: the client cannot see it, so the warning for `GLOBAL` names both cases.
- A close of the listeners when the server is killed, as `terminate()` does on Windows.

## Decisions

### 1. The warning picks its end by who started the server and by the registered scope

When the new session did not start its server process, as for `tcp://` and `pipe://<name>`, and the registered definition has the scope `GLOBAL`, the warning ends with "the remote library was imported again; its library scope is GLOBAL, so its server-side state is kept unless the server restarted". When the session started the server process, as for `stdio:` and `pipe:<command>`, and for the other scopes, it keeps "the remote library was imported again, so its server-side state was reset". The text says "library scope", so that it is not read as `rpc_scope=GLOBAL`.

The session notes that it started its server process when it starts it, which it does for exactly these URIs. Its resources are no proof: they drop the process once it has been reaped, which can happen before the warning if the new process exits at once. The registered definition is the one Robot Framework registered the keywords for. The definition of the new session has the same scope whenever the warning is logged, since `_check_definition()` fails the call otherwise.

*Alternatives considered:*

- The text for `GLOBAL` over `stdio:` and `pipe:<command>`, too. It would be true in a sense, since the new session has a new server process, but the client started that process itself and knows that the state is gone.
- Picking the end by the scheme of the URI. `pipe:` stands for a server that the client starts and for one that it does not, so the check would repeat the parsing of `_create_pipe_connection()`, and every later transport would need a case of its own.

### 2. The server keeps its finalize

`_robot_finalize_library()` stays as it is; the check of the finalize found no problem (see Context). The requirements on the server are pinned by tests only, each with a copy that makes it fail.

### 3. Each test of the server starts from a new server and depends on no other test

`atests/global_library.robot` starts a new server with the three counter libraries for each test and removes the events file of the listener first, so that each test sets up its own preconditions. Sessions one after the other run as nested Robot runs of `atests/_nested/counters.robot`, as `rpc_scope.robot` checks sessions across suites. Within one test, a session of `JsonRpcRemote` ends only with the test or the suite; a nested run is a client of its own, whose session ends with the run and finalizes its import. The test of the close stops the server; it carries the tag `posix`, as the other tests of a graceful stop do. The reconnect over TCP is tested in this suite, too, since the server of `connect_retry.robot` serves only `ConnectionLossLib`, which has the scope `TEST`.

The listener writes to a file with a fixed name in the temp directory, as `ConnectionLossLib` writes its record. A path among the import arguments would be part of the key under which Robot Framework caches the `GLOBAL` library. Servers of other suites that serve `GlobalCounterLib` write to the same file; that does not matter, since each test that reads it removes it first.

The reconnects to a server that the client started are tested in `stdio_connect_retry.robot` and `pipe_connect_retry.robot`. Each new test imports `GlobalCounterLib` itself, with `rpc_scope=TEST`, so that it has a server process of its own, and each test of these suites matches only the warning for its own URI. `pipe://<name>` gets no Robot test of its own: the choice of the text is the client's, which the unit test checks against the fake server on a real pipe, and on the server it is the same runner as over TCP.

## Risks / Trade-offs

- [A listener of a `GLOBAL` library sees a call once per client that has the library imported] → Robot Framework's behavior for several imports; the tests check that an event arrives, not how often.
- [The warning for `GLOBAL` on a server that the client did not start cannot say whether the state was kept] → It names both cases; the client has no way to know.
- [A server for each test and the nested runs cost time] → Seconds per test, for tests that depend on nothing else.

## Migration Plan

None.
