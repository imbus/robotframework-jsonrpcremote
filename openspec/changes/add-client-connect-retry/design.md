# Design

## Context

See proposal.md for the motivation and specs/client/spec.md for the requirements. This change builds on the whole series:

- **`fix-client-session-error-state`:** `_connect()` makes one attempt, returns only a started session and stops a timed-out one.
- **`fix-client-handshake-cleanup`:** a failed attempt closes its connection and reaps its `stdio` server.
- **`fix-client-stranded-calls`:** calls go through `submit()`, and the worker thread prints nothing.
- **`fix-client-lost-connection`:** loss detection, the cause, and the "was lost" / "lost while running keyword" errors. A lost session stays stored until `_stop_session()` (scope end).

Robot Framework registers the library's keywords, with their arguments, types and documentation, from the definition returned by the first session at import time. It does not ask again later.

## Goals / Non-Goals

**Goals:**

- One rule for all connection attempts when the opt-in is set.
- Fast failure while a server stays down, and immediate recovery once it is back.
- A reconnect after a loss is never silent, and never runs against a changed library.

**Non-Goals:**

- Retrying keyword calls. A call that was running at the loss fails and is not sent again (`fix-client-lost-connection`).
- Comparing the library definition when a new session starts at a scope boundary without a preceding loss. This was decided explicitly.
- Backoff strategies; the interval is fixed.

## Decisions

### 1. One parser for time options

`_time_option(name, value)` parses numbers, Robot time strings (`timestr_to_secs(..., round_to=None)`) and plain strings from Python. It rejects invalid and negative values with a `ValueError` that names the option.

`__init__` parses `rpc_timeout`, `rpc_connect_retry_timeout` and `rpc_connect_retry_interval` with it, and rejects an interval of 0 or less while retry is enabled, all before it connects. `self.__session` is assigned before the validation so that `__del__` works when the validation fails.

### 2. Connection state on the `JsonRpcRemote` instance

```
                    connect ok                      scope end
  [no session] -------------------> [session] -------------------> [no session]
       ^                                |
       |                                | lost (detected at next call)
       |              retry off         v
       |        +-------------------- [lost] ----------------------+
       |        v                                                  | retry on
  fail with "was lost"                                             v
  until scope end                                           reconnect within window
                                                             |        |        |
                                           ok, same definition|  ok, changed  | window passed
                                                             v        v        v
                                                  [session] + WARN  [incompatible]  [outage: window spent]
                                                                    fail until      each call: 1 attempt;
                                                                    scope end       success -> [session]
```

Two pieces of state live on the instance, not on the session, because they outlive it:

- **"Window spent":** cleared by any successful connection.
- **"Pending loss":** the cause of a loss that has not been reconnected yet. It decides whether the next successful connection counts as a reconnect, with a warning and a definition check. It is cleared on success or at the end of the scope.

### 3. A retry loop around `_connect()`

`_connect_with_retry()` calls `_connect()`:

- **Retry off:** once.
- **Retry on, window not spent:** until it succeeds or the window has passed, sleeping `min(interval, remaining)` between attempts.
- **Retry on, window spent:** exactly once.

When the window passes, it marks the window spent and raises `ConnectionError` with the URI, the window, the number of attempts and the last error, chained from that error. Each attempt stays bounded by `rpc_timeout` inside `_connect()`, so the total wait can exceed the window by at most one attempt.

`_start_session()` uses the loop for every new session. That covers the import (`__init__`), new sessions after a scope end, and lost sessions with retry on.

### 4. Replacing a lost session

With retry on, `_start_session()` turns a stored lost session into "pending loss": it records the cause as built by `fix-client-lost-connection`, drops the session and connects through the retry loop. If the next successful connection follows a pending loss:

- **Definition check:** It compares `session.library_definition` with the definition registered at import, using full dataclass equality. If they differ, it stops the new session and stores an "incompatible" error. This call and every further call raise that error without connecting, until `_stop_session()`.
- **Warning:** Otherwise it logs a warning with Robot's logger. We are on Robot's thread, inside the keyword call, so that works. Example: "Connection to '<uri>' was lost (<cause>). Reconnected after 3.2s (4 attempt(s)); the remote library was imported again, so its server-side state was reset." The cause already includes a `stdio` exit code.

### 5. The registered definition is captured at import

`__init__` keeps the `LibraryDefinition` of its first session, which is what Robot used to register the keywords. The definition check always compares against it, never against the previous session.

### 6. Logging for attempts without a loss

A connection that needed more than one attempt but did not follow a loss logs an INFO message, for example "Connected to '<uri>' after 2.4s (3 attempts)". It does not log a warning; the spec requires warnings only after a loss.

### 7. Documentation

The README argument list gets the two options and notes that `rpc_timeout` accepts time strings. The list of client options that are not forwarded gets the two options too. The section "Lost connections" from `fix-client-lost-connection` gets a part on the opt-in:

- when it applies, and what giving up means;
- the warning;
- the definition check;
- the reset of server-side state.

## Risks / Trade-offs

- **[Blocking the Robot thread]** Waiting for the server blocks the keyword call for up to the window plus one attempt, as connecting already blocks today. → That is intended; the window bounds it.
- **[Window spent across scopes]** If an outage outlasts the window, later tests fail fast until the server is back, even with a new scope. → That is the agreed "one window per outage". The first successful connection resets it.
- **[Definition compared only after a loss]** A new session at a scope boundary against an updated server is not checked, so keyword registrations may be stale. → Decided explicitly; same behavior as today.
- **[Strict comparison]** Equal libraries can still differ in `source` paths, for example a different install location after a redeploy. → Accepted as decided; the error message names the change, so such cases stay understandable.
