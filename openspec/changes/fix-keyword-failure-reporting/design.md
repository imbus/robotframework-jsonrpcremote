# Design

## Context

See proposal.md for the motivation and the decisions confirmed on 2026-10-31, and the delta specs of `client` and `server` for the behavior.

**Today:**

- On the server, `_robot_run_keyword` runs a keyword with Robot Framework's keyword runner. When the keyword fails, Robot's status reporter catches the exception, logs its message at FAIL and its traceback at DEBUG, and raises `HandlerExecutionFailed`. That exception carries the message as Robot formats it for a local keyword and the flags `skip`, `exit` and `continue_on_failure`. Its `__context__` is the original exception.
- The endpoint's `run_keyword` catches every exception, logs it with `logger.exception` and answers with `RunKeywordError(message=str(e))`.
- The server's Robot execution runs at log level INFO, so the DEBUG traceback never reaches the client, and neither does any DEBUG or TRACE message of a library (SERVER-16, checked on 2026-10-31: with the client at `--loglevel TRACE`, only the INFO message of a remote keyword arrived). The server forwards the messages that Robot gives its listener while a command of a client runs.
- The client raises `RuntimeError(f"Error executing keyword '{name}': {result.error}")`, so the message holds the `repr` of the error. On DEBUG, Robot logs the traceback of this `RuntimeError`, which is made of the client's asyncio frames.

**Checked on 2026-10-31:**

- **The client side in Robot (`robot/running/statusreporter.py`, `robot/utils/error.py`):**
  - For an exception that is a `RobotError`, Robot shows the message without the class name and logs `details` as the traceback at DEBUG; with empty `details` it logs no traceback.
  - It reads skip, continuable and fatal from the attributes `ROBOT_SKIP_EXECUTION`, `ROBOT_CONTINUE_ON_FAILURE` and `ROBOT_EXIT_ON_FAILURE`.
- **Robot's own Remote library** raises `robot.errors.RemoteError(message, details, fatal, continuable)` for this. It is a `RobotError`, the same in Robot Framework 7.2 and 7.5.
- **A `FatalError` in a remote keyword does not stop the server:** the next session runs keywords as before.
- **Robot's output** has `set_log_level`, which `Set Log Level` uses. Robot formats messages, such as its own TRACE lines `Arguments: [ … ]` and `Return: …`, only for levels that are enabled.

## Goals / Non-Goals

**Goals:**

- A failing remote keyword looks and behaves in Robot Framework as a failing local keyword: the same message, the traceback at DEBUG under the keyword, and skip, continuable and fatal failures.
- The log messages of a remote keyword reach the log at every level that the suite logs, and the server does not send or format messages below it.

**Non-Goals:**

- **Errors that are not failures of a keyword:** for example an unknown token or a server that is shutting down. They keep their message and get no traceback; `fix-rpc-error-responses` handles them.
- **Messages that a library logs while it is imported (SERVER-11):** they take another path in Robot and stay a backlog item.

## Decisions

### 1. The runner turns Robot's failure into the protocol's error

On the runner thread, `_robot_run_keyword` catches `ExecutionFailed` from the keyword runner and builds the `RunKeywordError` with a small function of its own:

- **message:** the message of the `ExecutionFailed`, which Robot has formatted for a local keyword;
- **type:** the name of the class of the original exception, the `__context__` of the failure;
- **traceback:** the traceback of the original exception, formatted with Robot's `ErrorDetails` as Robot does for a local keyword, so without Robot's own frames;
- **mode:** `SKIP` if the failure skips, else `FATAL` if it exits, else `CONTINUABLE` if it can continue, else none. This is the order in which Robot evaluates the flags.

It raises an exception of the server that carries this error. The endpoint answers with it, and keeps answering every other exception as today.

- **Alternative:** build the error in the endpoint from the exception that reaches it. The endpoint runs on the asyncio thread, apart from Robot; the runner thread is where Robot's types and `ErrorDetails` belong, and a function of its own can be tested without a running server.
- **Alternative:** call the keyword outside Robot's runner to get the original exception directly. Robot's runner applies argument conversion, timeouts and listeners, which the server relies on.

### 2. The server logs a failing keyword at DEBUG

A failing keyword is a test result, not an error of the server. The endpoint logs it at DEBUG with its message, instead of `logger.exception` with a traceback at ERROR, which appears on the console of `robot` for every failing keyword over stdio. Other exceptions keep `logger.exception`.

### 3. The client raises Robot's `RemoteError`

The client raises `robot.errors.RemoteError(message, traceback or "", fatal=mode is FATAL, continuable=mode is CONTINUABLE)` and sets `ROBOT_SKIP_EXECUTION` on it for `SKIP`. Robot Framework then does everything the specs ask:

- it shows the message without a name;
- it logs the remote traceback at DEBUG under the keyword, in place of the client's frames;
- it skips the test, continues it or stops the run.

A server that sends only a message gives a normal failure without a traceback.

- **Alternative:** the public exceptions of `robot.api` (`Failure`, `ContinuableFailure`, `FatalError`, `SkipExecution`), with the remote traceback logged by `logger.debug`. Robot would still log the client's own traceback at DEBUG, and the remote one would be a separate message before it.
- **Alternative:** a `RobotError` subclass of our own. It would repeat `RemoteError`, which Robot's Remote library uses for exactly this.

### 4. The client reports its log level, and the server runs each command at it

- **Protocol:** `InitializeParams` gets the optional field `log_level`, and a new notification `robot/set_log_level` with `SetLogLevelParams(log_level)` goes from the client to the server. The values are Robot Framework's level names, such as `DEBUG`.
- **Client:** at the start of a session it sends the current `${LOG LEVEL}` in `robot/initialize`. Before every keyword call it compares `${LOG LEVEL}` with the level it reported last in that session and sends `robot/set_log_level` if they differ, so `Set Log Level` takes effect at the next call.
- **Server:** the endpoint keeps the level of its client, INFO if the client reported none. The runner sets Robot's log level with `set_log_level` to the level of the client whose command it runs, before it runs the command. Robot then drops the messages below that level itself, and formats its TRACE lines only for a client that wants them.
- **The traceback reaches the client once:** at DEBUG, Robot on the server logs the traceback of a failure right after its FAIL or SKIP message, and the client would log it a second time from the error. The runner does not forward a DEBUG message that directly follows such a message in the same command. The check of the same command matters for a failure without a traceback, after which the next message belongs to the library.
- **The server's console stays as it is:** `set_log_level` also sets the root logger of Python's `logging`, so that the messages of libraries that use `logging` reach the client. The handler that prints to the server's stderr gets the server's own level, so a client at DEBUG does not bring the DEBUG messages of every library onto that console, which over stdio is the console of `robot`.

- **Alternative:** a field `log_level` in every `robot/run_keyword`. It needs no state on the server, but repeats the level in every call; Daniel chose `robot/initialize` with a notification.
- **Alternative:** run the server at TRACE, send every message and let Robot on the client filter, as the Remote library does. The server would format and send messages, including its own `Arguments` and `Return` lines, for clients that drop them.
- **Alternative:** filter on the server after Robot has logged at TRACE. Robot would still format every TRACE message.

### 5. The client marks DEBUG and TRACE messages from the server

At DEBUG and TRACE, the log holds messages of both sides under a remote keyword: at TRACE, Robot's lines `Arguments: [ … ]` and `Return: …` appear twice, and they can differ, because the server's line shows what the library really gets. The client puts `[remote] ` in front of every DEBUG and TRACE message from the server and in front of the traceback (decision confirmed on 2026-11-01). Messages at other levels stay unchanged: they are what a suite reads and matches most, and the keyword's owner `JsonRpcRemote` already shows where they come from.

- **Why the client:** it alone tells its own messages from those of the server, whichever server that is, and the protocol stays as it is. Robot's messages have no field for a source, so the mark has to be part of the text.
- **Alternative:** mark only Robot's `Arguments` and `Return` lines on the server, or drop them there as the traceback. The server would have to recognize these lines by their text, and library messages would stay unmarked.
- **Alternative:** mark messages at every level. It would change the text of the messages that listeners and log checks read most, as compared to a local library.

### 6. Tests run the failure modes in a Robot run of their own

- **Unit tests:**
  - the function of decision 1 with real `HandlerExecutionFailed` errors, raised from a `ValueError`, an `AssertionError`, `SkipExecution`, `ContinuableFailure` and `FatalError`;
  - the endpoint with a stub context that raises the server's failure exception and another exception;
  - the client with the fake server, which reports each mode, a traceback and a message only, and which records the log level in `robot/initialize` and in `robot/set_log_level`;
  - the endpoint and the runner with the level of the client: a command runs at it, INFO without one;
  - the real server over the protocol, without the client (`tests/test_server_end_to_end.py`): only there do the messages below a client's level show, because the client drops them too, and the fields of an error that the client does not read;
  - the example server, which also handles `robot/set_log_level`.
- **Robot tests:** skip, continuable and fatal failures show only in the result of a run, so a new suite runs a nested suite with `NestedRobot` and checks the status and message of each test.
  - `NestedRobot` gets a keyword that runs a suite whose tests may fail and returns the status and message of each test.
  - `atests/errors.robot` checks the exact messages.
  - The nested suite also checks that the server runs keywords after a fatal failure.
  - A suite with a remote keyword that logs at TRACE, DEBUG and INFO checks with `--loglevel DEBUG` and after `Set Log Level    TRACE` which messages reach the log.

### 7. The documentation describes failures and log levels as they are

- **New guide** "Failures of remote keywords", with an example in `docs/examples/failures/`: a library that fails normally, skips, fails continuably and fails fatally, and a suite with a test for each.
  - The page shows the library and the suite and says how each test ends.
  - The example's `run.sh` runs the suite with `--nostatusrc` and checks the status and message of each test with Robot's result API, so CI notices if a page promises a different result.
- **The protocol page** describes the fields of `RunKeywordError` as the server fills them and the client uses them, `log_level` in `InitializeParams` and the notification `robot/set_log_level`.
- **Getting started** says that the log messages of a remote keyword follow the log level of the suite, `--loglevel` and `Set Log Level` included, and what `[remote]` means.
- **Status and roadmap:** the failure modes move from Planned to Available today.

## Risks / Trade-offs

- **[`robot.errors` is internal to Robot Framework]** Robot's own Remote library uses `RemoteError` the same way. → The client's unit tests use it with the Robot Framework of the environment, and CI runs them with Robot Framework 7.2 and the latest version.
- **[Messages change for existing suites]** A pattern such as `*boom*` still matches, but one that expects `Error executing keyword` does not. → Before 1.0 that is no breaking change, and the guide shows the new messages.
- **[The mark changes the text of DEBUG and TRACE messages]** A listener or log check that matches such a message from a remote library sees the prefix, unlike with a local library. → It is limited to these levels, and Getting started explains it.
- **[Several clients on one server at different levels]** The server's Robot execution has one log level. → The runner sets it for each command to the level of the client whose command it is; commands run one after another (several-libraries guide).
- **[Messages outside a command]** Messages that arrive while no command runs are not forwarded today. → Unchanged; SERVER-11 covers those of the import.
