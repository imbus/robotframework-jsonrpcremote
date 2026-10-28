# Design

## Context

See proposal.md for the motivation and specs/ for the requirements.

**Server:** `_runner.py` imports the class `NotSet` from `robot.utils` and decides in `_robot_import_library` with `isinstance(arg.default, NotSet)` whether an argument has a default. Every Robot Framework 7 release marks a missing default with the singleton `robot.utils.NOT_SET`; only from 7.1 on is it an instance of a public class `NotSet`.

**Client, log forwarding today:**

- `_ClientEndpoint._log_notification` runs on the session's worker thread.
- While `run_keyword` is running, `callback_loop` holds Robot Framework's event loop, and the handler schedules `logger.write(message, level, html, console)` there with `call_soon_threadsafe()`. `run_keyword` sets `callback_loop` after it got its session and resets it in `finally`.
- At any other time the handler calls `logger.write` directly on the worker thread. Robot Framework only accepts log messages from the threads it runs tests in (`MainThread`, `RobotFrameworkTimeoutThread`) and silently drops the rest.
- `logger.write` has a `console` parameter only from 7.4 on; before, the fourth argument raises `TypeError`.

**When sessions start and end:**

- `JsonRpcRemote.__init__` starts the first session, so its import messages arrive while Robot Framework imports the library.
- Later sessions start inside `_start_session()`, reached through `_session` from `run_keyword` and the other dynamic API methods: after the end of an `rpc_scope`, when a lost session is replaced, and once per attempt of connect retry. Every attempt creates its own `_Session` with its own `_ClientEndpoint`.
- Sessions end in `_stop_session()`, called from the listener methods at the end of a test or suite and from `__del__`.

**What this project's server forwards** (checked on 2026-10-28): only the messages that Robot Framework passes to the `log_message` listener hook. Messages that a library logs while it is imported go to the server's syslog and execution errors instead and never reach the client. Messages logged while the server finalizes a library, for example from a library listener's `close`, are forwarded.

**What Robot Framework does with messages a local library logs during its import or from its listener when a test or suite ends** (checked on 2026-10-28 with 7.0 and 7.5): info messages go only to the syslog, except that 7.5 puts messages from the end of a test into that test; warnings and errors always also appear among the execution errors.

## Goals / Non-Goals

**Goals:**

- The server works on Robot Framework 7.2 and later, the new minimum (see the result in proposal.md).
- The client forwards log messages, including console messages, on Robot Framework 7.2 and later.
- No log message is dropped because it arrived on the wrong thread; Robot Framework receives every message from a thread it accepts, in arrival order.

**Non-Goals:**

- Timestamps: a message handed over later carries the time it reached Robot Framework, as the protocol sends no timestamp.
- Messages that arrive while the library instance is garbage collected or the interpreter exits; there is no Robot Framework thread left to take them.
- Error responses to failed notifications (`fix-peer-message-handling`); once `logger.write` no longer raises, the known cause is gone.
- Changes to the protocol or to what the server forwards. Forwarding the messages that a library logs while it is imported is left to a separate change; the client already handles them, since other servers may send them.

## Decisions

### 1. The server compares defaults with `robot.utils.NOT_SET` by identity

`_robot_import_library` checks `arg.default is NOT_SET`. The singleton exists and is the marker in every Robot Framework 7 release.

- **Alternative:** import `NotSet` with a fallback for 7.0. Two code paths for the same check, and the fallback would still have to know the 7.0 marker.
- With the minimum at 7.2, `NotSet` alone would work too; `NOT_SET` stays because the identity check is simpler.

### 2. The client detects the `console` parameter of `logger.write` once

At import time, the client checks whether `logger.write` accepts `console`. One helper writes every forwarded message: with `console` where it is supported, otherwise `logger.write(message, level, html)` followed by `logger.console(message)` when the message is marked for the console.

- **Alternative:** compare `robot.version`. Feature detection follows the real signature and needs no version table.
- **Alternative:** call with `console` and catch `TypeError`. It would also catch unrelated `TypeError`s and write some messages twice.

### 3. One log sink per library instance, shared by all its sessions

`JsonRpcRemote` owns a small thread-safe sink and hands it to every `_Session` it creates, and from there to its `_ClientEndpoint`. The notification handler only submits messages to the sink; the sink decides how they reach Robot Framework:

- **attached** (a keyword call is running): schedule the write on Robot Framework's loop, as today;
- **detached**: keep the message in a queue.

`run_keyword` attaches the loop instead of setting `callback_loop`, and detaches it in `finally`. Attaching first writes the queued messages, then stores the loop. A lock around submitting, attaching and detaching keeps the arrival order.

- **Why per instance:** connect retry and the replacement of a lost session create several sessions. A failed attempt can carry exactly the messages that explain its failure, for example a library constructor that logs and then raises; a queue per endpoint would be lost with the attempt.
- **Alternative:** a queue per `_ClientEndpoint`. Simpler, but loses the messages of discarded sessions.
- **Alternative:** a background logger package. A new dependency for the same effect, since it also writes only when the test thread logs next.

### 4. The queue is drained where control returns to Robot Framework's thread

The client writes the queued messages in the `finally` of `_start_session()` and `_stop_session()`, and when `run_keyword` attaches. This covers:

- the import (`__init__` starts the first session);
- a new session started by a keyword call, whose messages then land in that keyword's log;
- the replacement of a lost session and failed connection attempts;
- the end of a session at the end of its `rpc_scope`.

Draining never raises. Drained from `__del__` on another thread, Robot Framework drops the messages, which is the same as today.

- **Alternative:** drain at the start of every dynamic API method. More places with the same effect.

### 5. Tests drive the sink directly and through a fake server, and one Robot run checks Robot Framework's side

- **Unit tests:**
  - the sink's order and thread handling;
  - the console helper with the detection result patched to "unsupported";
  - the whole path through the fake server, which gains the ability to send log notifications while it imports. That covers order, the main thread, and messages of a failed import.
- **Robot test:** runs a small suite in a nested Robot process against a server whose library logs a warning from its listener's `close`, which the server calls when it finalizes the library at the end of the session's scope. The outer test reads the execution errors from the inner output file. Messages sent while the library is imported are covered by the fake-server tests only, because this project's server does not send them.
- **Version runs:** unit tests and Robot suites in one local environment per Robot Framework version, 7.0 to 7.5.

## Risks / Trade-offs

- **[The remote library's constructor messages still do not reach the client]** This project's server does not forward them. → A separate change; the client part is ready for them. Even then, info messages from an import stay out of `log.html`, as for local libraries; the documentation site from `add-documentation-site` describes it.
- **[7.0 breaks at runtime in a way the API check did not show]** → The version runs find it; the proposal's fallback raises the minimum to the oldest version that passes. This happened: 7.0 and 7.1 failed, and the minimum is now 7.2.
- **[A later Robot Framework changes `logger.write` again]** → Decision 2 reads the actual signature, so a renamed or removed parameter falls back to the separate console write instead of failing.
- **[More messages reach the execution errors]** Warnings logged while the server finalizes the library were silently lost before and are now visible. → Intended; it matches a local library.
