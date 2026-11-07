# client Specification

## Purpose

Defines the behavior of the `JsonRpcRemote` Robot Framework library: how it starts, uses and ends sessions with a remote server and how it reports failures to Robot Framework.

## Requirements

### Requirement: Keyword failures affect only their own call

When a keyword call fails, the client SHALL report the failure for that call only. This covers a remote keyword that raises, a server that answers the request with a JSON-RPC error, and a request that cannot complete. Later calls in the same session SHALL NOT re-raise that failure.

#### Scenario: Remote keyword raises

- **WHEN** a remote keyword raises an error
- **THEN** the call fails with that error
- **AND** the next keyword call in the same session returns its result

#### Scenario: Server answers a keyword call with a JSON-RPC error

- **WHEN** the server answers a keyword call with a JSON-RPC error
- **THEN** that call fails
- **AND** the next keyword call in the same session is sent to the server and returns its result

### Requirement: A failed session start is not kept

If starting a session fails because the server cannot be reached or the handshake fails, the client SHALL raise that error for the call that started the session and SHALL NOT keep the failed session. The next call SHALL make a new connection attempt.

#### Scenario: Server is not reachable when a session starts

- **WHEN** a session starts while the server is not reachable
- **THEN** the call that started it fails with the connection error
- **AND** the next call, made after the server became reachable, connects again and returns its result

#### Scenario: Server rejects the handshake

- **WHEN** the server rejects the handshake, for example because the requested library is not allowed
- **THEN** the call that started the session fails with the server's error
- **AND** the next call makes a new connection attempt instead of re-raising that error

### Requirement: A timed-out session start is stopped

If a session does not finish starting within `rpc_timeout`, the client SHALL stop it, closing any connection it opened, and SHALL raise a `TimeoutError`. The next call SHALL make a new connection attempt.

#### Scenario: Server accepts the connection but never answers the handshake

- **WHEN** the server accepts the connection but does not answer the handshake within `rpc_timeout`
- **THEN** the call fails with a `TimeoutError`
- **AND** the client closes the connection it opened
- **AND** the next call opens a new connection

### Requirement: A failed session start releases its resources

If starting a session fails, the client SHALL close the connection it opened before it reports the failure. For the `stdio` transport, it SHALL also wait for the server process it spawned to exit, terminating and finally killing it if it does not exit within `rpc_timeout`, before it reports the failure.

#### Scenario: Handshake fails over TCP

- **WHEN** the server rejects the handshake of a session over TCP
- **THEN** the call that started the session fails with the server's error
- **AND** the client has closed the connection

#### Scenario: Handshake fails over stdio

- **WHEN** the server spawned for a `stdio:` URI rejects the handshake
- **THEN** the call that started the session fails with the server's error
- **AND** the spawned server process has exited by the time the failure is reported

### Requirement: Calls never hang on an ended session

A keyword call on a session whose connection handling has ended, or ends before the call has started, SHALL fail with a `ConnectionError`. It SHALL NOT wait forever.

#### Scenario: Call on a session that has ended

- **WHEN** a keyword call is made on a session whose connection handling has already ended
- **THEN** the call fails at once with a `ConnectionError`

#### Scenario: Session ends before the call starts

- **WHEN** a keyword call has been handed over to the session
- **AND** the session's connection handling ends before the call has started
- **THEN** the call fails with a `ConnectionError`

### Requirement: Ending a session never raises

Ending a session SHALL NOT raise. This covers the end of its `rpc_scope`, garbage collection of the library instance, and interpreter exit. Each teardown step SHALL be bounded by `rpc_timeout`, also when the connection or the session's worker do not respond.

#### Scenario: Worker does not respond to the teardown

- **WHEN** a session is ended while its worker does not process the teardown
- **THEN** ending it returns after a bounded time
- **AND** no exception is raised

#### Scenario: Session's event loop is already closed

- **WHEN** a session is ended after its event loop has been closed
- **THEN** ending it returns without raising

### Requirement: Session errors are not printed by the worker thread

Errors that end a session's worker thread SHALL be reported to the caller that is affected by them: the call that started the session, or the keyword call that failed. They SHALL NOT be printed as an unhandled thread exception.

#### Scenario: Session fails to start

- **WHEN** a session fails to start because the server is not reachable
- **THEN** the call that started it fails with the connection error
- **AND** no unhandled exception of the session's worker thread is reported

#### Scenario: Closing the connection is cancelled from outside the session

- **WHEN** a session ends
- **AND** waiting for its connection to close is cancelled by something other than the session itself
- **THEN** the session still releases its connection and, over stdio, reaps its server process
- **AND** no unhandled exception of the session's worker thread is reported

### Requirement: A lost connection fails every later call until the session ends

When the connection of an established session ends without the client closing it and connect retry is not enabled, every following keyword call in that session SHALL fail with a `ConnectionError` whose message is "Connection to '<uri>' was lost: <cause>". This SHALL last until the session ends according to `rpc_scope`. Without connect retry, the client SHALL NOT reconnect on its own.

#### Scenario: Server goes away while the session is idle

- **WHEN** connect retry is not enabled
- **AND** the server goes away while no keyword is running
- **AND** the next keyword call is made
- **THEN** the call fails with `ConnectionError: Connection to '<uri>' was lost: <cause>`

#### Scenario: Further calls in the same session

- **WHEN** connect retry is not enabled
- **AND** the connection of the session has been lost
- **AND** several further keyword calls are made in the same session
- **THEN** each of them fails with the same lost-connection error
- **AND** none of them opens a new connection

#### Scenario: Session ends according to its scope

- **WHEN** the connection of a session with `rpc_scope` `TEST` has been lost
- **AND** the test ends
- **AND** the server is reachable again when the next test makes a keyword call
- **THEN** the call starts a new session and returns its result

### Requirement: The lost-connection message names the cause

The cause in a lost-connection message SHALL be "the connection was closed by the server" when the server closed the connection cleanly. Otherwise it SHALL be the type and message of the error that ended the connection. For the `stdio` transport, the cause SHALL also name the exit code of the server process.

#### Scenario: Server closes the connection cleanly

- **WHEN** the server closes the connection cleanly
- **THEN** the cause in the message is "the connection was closed by the server"

#### Scenario: Connection ends with an error

- **WHEN** the connection ends because of an error, for example a reset connection
- **THEN** the cause in the message names the error's type and message

#### Scenario: stdio server process exits

- **WHEN** the server process spawned for a `stdio:` URI exits with exit code 3
- **THEN** the cause in the message states that the server process exited with code 3

### Requirement: A keyword running when the connection is lost fails and is not sent again

A keyword call that is running when the connection is lost SHALL fail with a `ConnectionError` whose message is "Connection to '<uri>' was lost while running keyword '<name>': <cause>". The client SHALL NOT send that call again.

#### Scenario: Server goes away during a keyword call

- **WHEN** the server goes away while a keyword call is running
- **THEN** the call fails with `ConnectionError: Connection to '<uri>' was lost while running keyword '<name>': <cause>`
- **AND** the server received the call exactly once

### Requirement: Ending a session on the client side is not a loss

When the client ends a session itself, at the end of its `rpc_scope` or when the library is torn down, it SHALL NOT treat that as a lost connection. The next call SHALL start a new session.

#### Scenario: Test with rpc_scope TEST ends

- **WHEN** a test with a session in `rpc_scope` `TEST` ends
- **AND** the next test makes a keyword call
- **THEN** the call starts a new session and returns its result instead of failing with a lost-connection error

### Requirement: Connect retry is an opt-in configured by two options

The client SHALL accept `rpc_connect_retry_timeout`, defaulting to 0 (connect retry disabled), and `rpc_connect_retry_interval`, defaulting to 1 second. Both options and `rpc_timeout` SHALL accept seconds or Robot Framework time strings, also as plain strings. The client SHALL reject invalid or negative values, and an interval of 0 while retry is enabled, at import. These options SHALL NOT be forwarded to the remote library.

#### Scenario: Options given as Robot time strings

- **WHEN** the library is imported with `rpc_connect_retry_timeout=1 minute`, `rpc_connect_retry_interval=2s` and `rpc_timeout=15s`
- **THEN** the client waits up to 60 seconds for a connection, retries every 2 seconds and limits each attempt to 15 seconds

#### Scenario: Invalid option value

- **WHEN** the library is imported with `rpc_connect_retry_timeout=soon`
- **THEN** the import fails with an error that names `rpc_connect_retry_timeout`

#### Scenario: Interval of zero while retry is enabled

- **WHEN** the library is imported with `rpc_connect_retry_timeout=10s` and `rpc_connect_retry_interval=0`
- **THEN** the import fails with an error that names `rpc_connect_retry_interval`

#### Scenario: Options are not forwarded

- **WHEN** the library is imported with the connect retry options and a named init argument for the remote library
- **THEN** the remote library receives only its own init argument

### Requirement: With connect retry every connection attempt is repeated within the window

When connect retry is enabled and a connection attempt fails, the client SHALL try again every `rpc_connect_retry_interval` until an attempt succeeds or `rpc_connect_retry_timeout` has passed. This SHALL apply at library import, when a new session starts and when a lost session is replaced. Each attempt SHALL be limited by `rpc_timeout`.

#### Scenario: Server comes up during the library import

- **WHEN** connect retry is enabled
- **AND** the server starts accepting connections a few seconds after the library import began
- **THEN** the import waits and succeeds

#### Scenario: Server is down when a new session starts

- **WHEN** connect retry is enabled
- **AND** a test with `rpc_scope` `TEST` makes its first keyword call while the server is still starting
- **THEN** the call waits until the server accepts connections and returns its result

### Requirement: Connect retry gives up once per outage

If the window passes without a successful connection, the waiting call SHALL fail with a `ConnectionError` naming the URI, the window, the number of attempts and the last error. Until a connection succeeds again, every further call SHALL make exactly one connection attempt without waiting. After a successful connection, the next outage SHALL get the full window again.

#### Scenario: Server stays down

- **WHEN** connect retry is enabled with a window of 2 seconds
- **AND** the server stays down
- **THEN** the first call fails after about 2 seconds with a `ConnectionError` naming the URI, the window, the number of attempts and the last error
- **AND** the next call fails after a single connection attempt, without waiting for the window

#### Scenario: Server comes back after the window expired

- **WHEN** connect retry gave up during an outage
- **AND** the server is reachable again
- **THEN** the next call connects and returns its result
- **AND** a later outage again gets the full window

### Requirement: A reconnect after a lost connection is logged as a warning

When connect retry is enabled, the next call after a lost connection SHALL replace the session. That re-imports the remote library. On success, the client SHALL log a warning naming the cause of the loss, the time until it reconnected, the number of attempts, and that the library's server-side state was reset. Connection attempts that do not follow a lost connection SHALL NOT log a warning.

#### Scenario: Server restarts while the session is idle

- **WHEN** connect retry is enabled
- **AND** the server restarts while the session is idle
- **AND** the next keyword call is made
- **THEN** the call returns its result
- **AND** a warning names the cause of the loss, the time until it reconnected, the number of attempts and the reset of the server-side state

#### Scenario: stdio server process exited

- **WHEN** connect retry is enabled for a `stdio:` URI
- **AND** the server process exits with exit code 3 during a keyword call
- **THEN** that keyword call fails and is not sent again
- **AND** the next call starts a new server process and returns its result
- **AND** the warning names exit code 3

### Requirement: A changed library definition after a reconnect makes the library unusable until the session ends

After reconnecting following a lost connection, the client SHALL compare the definition of the remote library, including its name, with the one registered when the library was imported. If they differ, it SHALL close the new session and fail the call with a `ConnectionError` stating that the library definition changed. Every further call SHALL fail the same way, without connecting, until the session ends according to `rpc_scope`.

#### Scenario: Server comes back with the same library

- **WHEN** connect retry is enabled
- **AND** the server restarts with the same library, which it imports as a new instance
- **THEN** the next call returns its result

#### Scenario: Server comes back with a different library version

- **WHEN** connect retry is enabled
- **AND** the server restarts with a library whose definition differs from the one registered at import
- **THEN** the next call fails with a `ConnectionError` stating that the library definition changed
- **AND** further calls in the same session fail the same way without opening a connection
- **AND** after the session ended according to `rpc_scope`, the next call starts a new session

#### Scenario: Server comes back with a library of another name

- **WHEN** connect retry is enabled
- **AND** the server restarts with a library whose definition differs from the one registered at import only in its name
- **THEN** the next call fails with a `ConnectionError` stating that the library definition changed

### Requirement: Server log messages are forwarded on every supported Robot Framework version

The client SHALL write every log message that the server sends during a keyword call to Robot Framework's log of that call, with the message's level and HTML flag. This SHALL hold on every Robot Framework version from the minimum that the client's package declares.

#### Scenario: Oldest supported Robot Framework version

- **WHEN** the tests run with the oldest Robot Framework version that the client's package declares
- **AND** a remote keyword logs a message at level INFO
- **THEN** the message appears in Robot Framework's log of that keyword call at level INFO

#### Scenario: HTML message

- **WHEN** a remote keyword logs a message as HTML
- **THEN** the message appears in Robot Framework's log of that keyword call as HTML

### Requirement: Console messages from the server reach the console

When the server marks a log message for the console, the client SHALL write it to Robot Framework's log and to the console. This SHALL also hold on Robot Framework versions before 7.4.

#### Scenario: Console message on a Robot Framework version before 7.4

- **WHEN** the tests run with a Robot Framework version before 7.4
- **AND** the server sends a log message marked for the console during a keyword call
- **THEN** the message appears in Robot Framework's log of that keyword call
- **AND** the message is written to the console

### Requirement: Log messages outside a keyword call are handled like those of a local library

The client SHALL NOT drop a log message that the server sends while no keyword call is running. It SHALL hand the message to Robot Framework from the thread that runs the tests as soon as control returns there, keeping the order in which the messages arrived. Robot Framework then treats it like a message that a local library logs at the same moment.

#### Scenario: Server sends a warning while the library is imported

- **WHEN** the server sends a warning while the remote library is imported
- **THEN** the warning appears among Robot Framework's execution errors, as a warning that a local library logs during its import does

#### Scenario: Server sends an info message while the library is imported

- **WHEN** Robot Framework's syslog is enabled
- **AND** the server sends an info message while the remote library is imported
- **THEN** the message appears in the syslog, as an info message that a local library logs during its import does

#### Scenario: A keyword call starts a new session

- **WHEN** a keyword call starts a new session, for example in the next test with `rpc_scope=TEST`
- **AND** the server sends a log message while the remote library is imported again
- **THEN** the message appears in Robot Framework's log of that keyword call

#### Scenario: Remote library logs a warning when its session ends with its scope

- **WHEN** a session ends with its `rpc_scope`
- **AND** the remote library logs a warning while the server finalizes it
- **THEN** the warning appears among Robot Framework's execution errors, as a warning that a local library's listener logs at that moment does

#### Scenario: Messages keep their order

- **WHEN** the server sends several log messages while no keyword call is running
- **THEN** Robot Framework receives them in the order in which the server sent them

### Requirement: Ending a session does not wait for a worker that has ended

When a session is ended while its worker has already ended or ends meanwhile, ending it SHALL return as soon as the worker has ended, without waiting for `rpc_timeout`. It SHALL NOT leave behind a coroutine or task that Python reports as never awaited or as destroyed while pending.

#### Scenario: Lost session ends with its scope

- **WHEN** the connection of a session has been lost
- **AND** the session ends according to its `rpc_scope` while its worker is just finishing
- **THEN** ending it returns well within `rpc_timeout`
- **AND** Python reports no coroutine that was never awaited and no task that was destroyed while pending

#### Scenario: Worker has already ended

- **WHEN** the worker of a session has ended, but its event loop is not closed yet
- **AND** the session is ended
- **THEN** ending it returns at once
- **AND** Python reports no coroutine that was never awaited

#### Scenario: Connect retry replaces a lost session

- **WHEN** connect retry is enabled
- **AND** a keyword call finds the connection of its session lost and connects again
- **THEN** ending the lost session does not delay the call by `rpc_timeout`

### Requirement: `rpc_scope` accepts the scope names as strings

The client SHALL accept `rpc_scope` as a `SessionScope` member or as the name of one. It SHALL convert a name the way Robot Framework converts an argument to `SessionScope`, ignoring case, spaces and underscores, also when the name comes from Python code. An unknown name SHALL fail the import with an error that lists the valid names.

#### Scenario: Library built on the client passes the scope as a string

- **WHEN** Robot Framework imports a library that subclasses the client and passes `rpc_scope="TEST"`
- **THEN** each test of the suite runs in a session of its own

#### Scenario: Name in a different spelling

- **WHEN** the client is created from Python with `rpc_scope="test"`
- **THEN** its session ends with each test, as with `SessionScope.TEST`

#### Scenario: Unknown name

- **WHEN** the client is created with `rpc_scope="weekly"`, from Python or from a `.robot` file
- **THEN** the import fails with an error that lists `GLOBAL`, `SUITE` and `TEST`

### Requirement: A failed remote keyword fails with the server's message

When a remote keyword fails, the client SHALL fail the keyword call with exactly the message that the server reports for it, without a prefix and without the protocol's error record, as Robot Framework fails a local keyword with the message of its error.

#### Scenario: Remote keyword raises a ValueError

- **WHEN** a remote keyword raises `ValueError("bad value")`
- **THEN** the keyword call fails with the message `ValueError: bad value`

#### Scenario: Remote keyword fails an assertion

- **WHEN** a remote keyword raises `AssertionError("boom")`
- **THEN** the keyword call fails with the message `boom`

### Requirement: A skipped remote keyword skips the test

When the server reports that a remote keyword skipped the test, the client SHALL skip the test with the reported message, as Robot Framework does when a local keyword skips it.

#### Scenario: Remote keyword raises SkipExecution

- **WHEN** a remote keyword raises `SkipExecution("not today")`
- **THEN** the test is skipped with the message `not today`

### Requirement: A continuable failure of a remote keyword lets the test continue

When the server reports a continuable failure of a remote keyword, the client SHALL fail the keyword call as a continuable failure, so that the test runs on and fails at its end with the reported message, as with a local keyword.

#### Scenario: Remote keyword raises ContinuableFailure

- **WHEN** a remote keyword raises `ContinuableFailure("go on")` and the test has further keywords
- **THEN** the further keywords of the test run
- **AND** the test fails with the message `go on`

### Requirement: A fatal failure of a remote keyword stops the run

When the server reports a fatal failure of a remote keyword, the client SHALL fail the keyword call as a fatal error, so that Robot Framework stops the run as it does after a fatal error of a local keyword.

#### Scenario: Remote keyword raises FatalError

- **WHEN** a remote keyword raises `FatalError("stop all")` and the suite has further tests
- **THEN** the test fails with the message `FatalError: stop all`
- **AND** the further tests are not run and fail as stopped by a fatal error

### Requirement: The traceback of a failed remote keyword is logged at DEBUG level

When the server reports the traceback of a failed remote keyword, the client SHALL write it to the log at DEBUG level, as Robot Framework logs the traceback of a failed local keyword.

#### Scenario: Traceback of a failed remote keyword

- **WHEN** a remote keyword raises an error and the server reports its traceback
- **THEN** the log contains that traceback once at DEBUG level under the failed keyword, marked as described in "Debug and trace messages from the server are marked in the log"

### Requirement: A failure that a server reports with a message only is a normal failure

The failure mode, the type and the traceback of a failed remote keyword are optional. When the server reports a failure with a message only, the client SHALL fail the keyword call with that message as a normal failure.

#### Scenario: Server reports only a message

- **WHEN** the server reports a failed remote keyword with the message `boom` and no other fields
- **THEN** the keyword call fails with the message `boom`
- **AND** the test does not continue after it and is not skipped

### Requirement: The client reports its log level to the server

When a session starts, the client SHALL tell the server the log level of the Robot Framework run. When the log level has changed since the client last reported it, for example by `Set Log Level`, the client SHALL report the new level before its next keyword call in that session.

#### Scenario: Log level at the start of a session

- **WHEN** the suite runs with `--loglevel DEBUG` and a session starts
- **THEN** the client reports the log level `DEBUG` to the server

#### Scenario: Log level changed during the run

- **WHEN** a test calls `Set Log Level    TRACE` and then a remote keyword
- **THEN** the client reports the log level `TRACE` to the server before that keyword call

### Requirement: Debug and trace messages from the server are marked in the log

The client SHALL put `[remote] ` in front of the log messages at DEBUG and TRACE level that a server sends and in front of the traceback of a failed remote keyword, so that they can be told from the client's own messages at these levels, such as Robot Framework's `Arguments` and `Return` lines. Messages at other levels SHALL appear unchanged.

#### Scenario: Debug message from the server

- **WHEN** the server sends the log message `details` at DEBUG level
- **THEN** the log contains `[remote] details` at DEBUG level

#### Scenario: Robot Framework's trace lines from both sides

- **WHEN** the suite runs at TRACE level and calls a remote keyword with the argument `value`
- **THEN** the log contains `Arguments: [ 'value' ]` from the client
- **AND** `[remote] Arguments: [ 'value' ]` from the server

#### Scenario: Info message from the server

- **WHEN** the server sends the log message `hello` at INFO level
- **THEN** the log contains `hello` at INFO level

#### Scenario: Traceback of a failed remote keyword is marked

- **WHEN** the server reports a traceback that starts with `Traceback (most recent call last):`
- **THEN** the message at DEBUG level starts with `[remote] Traceback (most recent call last):`

### Requirement: A protocol-level error fails a keyword call with its message

When the server answers a keyword call with a JSON-RPC error, the client SHALL fail the keyword call with exactly the message of the error, without its code, the name of an exception or its data, as a normal failure. The data of the error SHALL go to the log at DEBUG level under the keyword, marked with `[remote] `.

#### Scenario: Unknown keyword

- **WHEN** the server answers a keyword call with the code `-32001` and the message `Keyword 'Gone' not found in library 'MyLibrary'.`
- **THEN** the keyword call fails with the message `Keyword 'Gone' not found in library 'MyLibrary'.`
- **AND** the test does not continue after it and is not skipped

#### Scenario: Data of the error

- **WHEN** the server answers a keyword call with a JSON-RPC error with the message `boom` and the data `details`
- **THEN** the keyword call fails with the message `boom`
- **AND** the log contains `[remote] details` at DEBUG level under the failed keyword

### Requirement: A protocol-level error fails the start of a session with its message

When the server answers the library import of a new session with a JSON-RPC error, the call that started the session SHALL fail with the message of the error, without its code, the name of an exception or the client's own traceback. At a library import, the data of the error SHALL follow the message, marked with `[remote] `, as Robot Framework shows the traceback of a local library that fails to import.

#### Scenario: Refused library import

- **WHEN** the server answers the import of `JsonRpcRemote` in a suite with the message `Library 'OtherLibrary' is not available.`
- **THEN** the import fails with an error that reads `failed: Library 'OtherLibrary' is not available.` after Robot Framework's introduction
- **AND** the error holds neither `RPC Error` nor a traceback

#### Scenario: Data of the error at a library import

- **WHEN** the server answers the import of `JsonRpcRemote` in a suite with the message `boom` and the data `details`
- **THEN** the import error holds the message `boom`, followed by `[remote] details`

#### Scenario: Refused import when a later session starts

- **WHEN** `rpc_scope` is `TEST` and the server answers the import of the next test's session with the message `Library 'OtherLibrary' is not available.`
- **THEN** the keyword call that started the session fails with the message `Library 'OtherLibrary' is not available.`

### Requirement: A connection reset while a session starts fails only the call that started it

If the connection is reset while a session starts, the client SHALL raise a connection error for the call that started the session and SHALL NOT keep the session. The Robot Framework run SHALL go on as after any other failed call: later tests and teardowns run, and the output files are complete.

#### Scenario: Reset during the library import

- **WHEN** a suite imports the library
- **AND** the connection is reset before the server has answered the handshake
- **THEN** the import fails with a connection error, which Robot Framework lists as an execution error
- **AND** the tests of the suite still run
- **AND** the run ends with a complete output file

#### Scenario: Reset when a later session starts

- **WHEN** a keyword call starts a new session
- **AND** the connection is reset before the server has answered the handshake
- **THEN** the keyword fails with a connection error, which `Run Keyword And Expect Error` can expect
- **AND** the next test runs
- **AND** the next call, made after the server became reachable, connects again and returns its result

#### Scenario: Every attempt of connect retry is reset

- **WHEN** connect retry is enabled
- **AND** every attempt within the window is reset before the server has answered the handshake
- **THEN** the call fails with the error that names the window and the number of attempts
- **AND** the run goes on

#### Scenario: The error chain has an end

- **WHEN** a session fails to start because of a connection reset
- **THEN** the error has the reset as its cause
- **AND** following the causes and contexts of the error comes to an end

#### Scenario: Asyncio reports nothing

- **WHEN** a session fails to start because of a connection reset
- **THEN** asyncio reports no exception that was never retrieved

### Requirement: JSON values from the server keep their nesting

The client SHALL accept return values and argument defaults that hold lists and objects nested to any depth, and SHALL hand them over unchanged.

#### Scenario: Return value with nested objects

- **WHEN** a server answers a keyword call with the result `[{"id": 1}, {"id": [2, 3]}]`
- **THEN** the keyword returns that list, with the same objects and lists in it

#### Scenario: Argument default with nested values

- **WHEN** a library definition has an argument with the default `{"a": [1, 2]}`
- **THEN** the argument of the keyword has that dict as its default

#### Scenario: Boolean as a return value

- **WHEN** a server answers a keyword call with a boolean
- **THEN** the keyword returns that boolean, not a number

### Requirement: The source of a remote keyword comes with its line

The client SHALL report the source of a remote keyword to Robot Framework together with the line that the server reports for it, so that what reads the source, such as the spec files of Libdoc and listeners, gets the same as for a local library.

#### Scenario: Source and line

- **WHEN** the server reports the source `/srv/MyLibrary.py` and the line `14` for a keyword
- **THEN** Robot Framework has that source and that line for the keyword

#### Scenario: Spec file of Libdoc

- **WHEN** Libdoc writes a JSON or XML spec file for a remote library whose server reports the lines of its keywords
- **THEN** the spec file holds for each keyword its source and its line

#### Scenario: Source without a line

- **WHEN** the server reports a source and no line for a keyword
- **THEN** Robot Framework has that source and no line for the keyword

#### Scenario: Line without a source

- **WHEN** the server reports a line and no source for a keyword
- **THEN** Robot Framework has no line for the keyword, because it would otherwise pair that line with the source file of the client

### Requirement: Problems that the peer reports reach Robot Framework

The client SHALL write every problem that its peer reports to Robot Framework's log as an error, which also puts it on the console and among the execution errors. The message SHALL name the URI of the server and the problem. A report SHALL NOT fail a keyword call by itself.

#### Scenario: Message without a valid length during a keyword call

- **WHEN** a keyword call is running
- **AND** the server sends a message with the header `Content-Length: abc`
- **THEN** an error that names the URI of the server and holds `abc` appears in Robot Framework's log and on the console
- **AND** the keyword call keeps waiting for its response

#### Scenario: Keyword call that gets its response after a report

- **WHEN** the server sends a message that the peer cannot read during a keyword call
- **AND** a valid response to the keyword call follows
- **THEN** the keyword passes
- **AND** the error stays among Robot Framework's execution errors

#### Scenario: Message without a valid length while the library is imported

- **WHEN** the server answers `robot/initialize` with the header `Content-Length: abc`
- **THEN** the library import fails with a timeout after `rpc_timeout`
- **AND** an error that holds `abc` appears among Robot Framework's execution errors

#### Scenario: Log message with params that cannot be converted

- **WHEN** the server sends a `robot/log` notification whose params cannot be converted
- **THEN** an error that names `robot/log` appears among Robot Framework's execution errors

#### Scenario: Error response without an id

- **WHEN** the server sends an error response with `id: null`, the code `-32700` and the message `bad`
- **THEN** an error that holds the code and the message appears among Robot Framework's execution errors

### Requirement: A log message from the server reaches the console as that of a local library

A log message that does not say whether it is for the console SHALL be handled as Robot Framework handles such a message of a local library: `WARN` and `ERROR` go to the console, other levels do not. On Robot Framework 7.4 and later, `console: false` SHALL keep a message off the console.

#### Scenario: Warning from a remote keyword

- **WHEN** a remote keyword logs a warning or an error
- **THEN** the message appears in Robot Framework's log and on the console, on every supported Robot Framework version

#### Scenario: Info message from a remote keyword

- **WHEN** a remote keyword logs a message at level INFO
- **THEN** the message appears in Robot Framework's log and not on the console

#### Scenario: Warning that is not for the console

- **WHEN** the tests run with Robot Framework 7.4 or later
- **AND** the server sends a warning with `console: false`
- **THEN** the warning appears in Robot Framework's log and not on the console

### Requirement: Argument defaults from the server are used as they arrive

The client SHALL hand every argument default of a library definition to Robot Framework as it arrives and SHALL NOT decode a pickle in it, so that importing a library runs no code from the server on the client. A call without an argument that has a default SHALL send neither the argument nor its default.

#### Scenario: Default as text with a type that the client does not know

- **WHEN** a library definition has a keyword with the argument `button` of the type `Button`, which the client cannot import, and the default `"LEFT"`
- **THEN** the keyword is available in Robot Framework
- **AND** Libdoc shows the argument as `button: Button = LEFT`

#### Scenario: Default that holds a pickle

- **WHEN** a library definition has the default `{"__pickled__": "<hex>"}`, whose pickle names a module that the client does not have
- **THEN** the keyword is available in Robot Framework
- **AND** the argument has that dict as its default, unchanged

#### Scenario: Call without an argument that has a default

- **WHEN** a keyword has the arguments `f` and `g`, both with defaults
- **AND** it is called once without arguments and once with only `g=5`
- **THEN** neither call sends a value for `f` to the server

### Requirement: The stdio transport works on Windows

On Windows, the client SHALL start the server of a `stdio:` URI and talk to it over its stdin and stdout, as on other platforms, with the requirements for sessions, lost connections and connect retry holding there too.

#### Scenario: Python server

- **WHEN** a suite on Windows uses a `stdio:` URI with `robot-jsonrpcremote-server --stdio`
- **THEN** keywords run and return their results, log messages reach the Robot Framework log, and a failing keyword fails only its call

#### Scenario: Server in another language

- **WHEN** a suite uses a `stdio:` URI with a server written in Node that reads its stdin and writes its stdout with one reader and one writer
- **THEN** keywords run and return their results, with a message of 1 MiB passing in both directions
- **AND** this holds on Linux and macOS as well

#### Scenario: Server that exits during a call

- **WHEN** the server process exits with exit code 3 during a keyword call
- **THEN** the call fails with the lost-connection error that names the exit code

#### Scenario: Wrapper script

- **WHEN** the command of the `stdio:` URI is a `.cmd` file that starts the server
- **THEN** keywords run and return their results

### Requirement: On Windows a backslash in a stdio command is an ordinary character

On Windows, the client SHALL treat a backslash in the command of a `stdio:` URI as an ordinary character, while quotes still group an argument. On other platforms, the client SHALL go on splitting the command as a POSIX shell does.

#### Scenario: Path with backslashes

- **WHEN** the URI is `stdio:C:\path\to\python.exe -m robot_jsonrpcremote_server --stdio Lib`
- **THEN** the client starts `C:\path\to\python.exe` with the remaining arguments

#### Scenario: Quoted path with a space

- **WHEN** the URI is `stdio:"C:\Program Files\tool\server.exe" --stdio`
- **THEN** the client starts `C:\Program Files\tool\server.exe` with the argument `--stdio`

#### Scenario: Backslash on POSIX

- **WHEN** the URI on a POSIX system is `stdio:server my\ library`
- **THEN** the client starts `server` with the single argument `my library`, as before

### Requirement: On Windows a session does not depend on the event loop policy

On Windows, the client SHALL run its session on a proactor event loop, whatever event loop policy the process has set.

#### Scenario: A library has set the selector policy

- **WHEN** the process has set `asyncio.WindowsSelectorEventLoopPolicy`, and a suite uses a `stdio:` URI
- **THEN** the session starts, and keywords run and return their results
