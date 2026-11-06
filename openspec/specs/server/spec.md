# server Specification

## Purpose

Defines the behavior of the `robot-jsonrpcremote-server` runtime: hosting Robot Framework libraries for connected clients over the supported transports, and starting and stopping cleanly.

## Requirements

### Requirement: Stopping closes client connections and exits

When the server is asked to stop (SIGTERM or SIGINT), it SHALL close every client connection, and the process SHALL exit with exit code 0 within a bounded time once no keyword is running anymore. This SHALL hold on every supported Python version and whether or not clients are connected.

#### Scenario: Idle client is connected

- **WHEN** a client is connected and no keyword is running
- **AND** the server receives SIGTERM
- **THEN** the client's connection is closed by the server
- **AND** the server process exits with exit code 0 within 10 seconds, without being killed

#### Scenario: No client is connected

- **WHEN** no client is connected
- **AND** the server receives SIGTERM
- **THEN** the server process exits with exit code 0 within 10 seconds, without being killed

### Requirement: Requests that can no longer run are rejected

Requests that need the Robot runner (importing or finalizing a library, running a keyword) and that are still waiting when the stop begins, or arrive afterwards, SHALL NOT be executed. The server SHALL answer them with an error stating that the server is shutting down. None of them SHALL stay unanswered.

#### Scenario: Keyword call is waiting when the stop begins

- **WHEN** a keyword call is waiting for the runner
- **AND** the stop begins
- **THEN** the call is answered with an error stating that the server is shutting down
- **AND** the keyword is not executed

#### Scenario: Keyword call arrives after the stop began

- **WHEN** the stop has begun
- **AND** a keyword call arrives before the client's connection is closed
- **THEN** the call is answered with an error stating that the server is shutting down
- **AND** the keyword is not executed

### Requirement: The result of a running keyword is delivered

A keyword that is running when the stop begins SHALL run to completion. The server SHALL deliver its result to the client before it closes that client's connection.

#### Scenario: Server is stopped during a keyword call

- **WHEN** a keyword is running
- **AND** the server receives SIGTERM
- **THEN** the client receives the keyword's result
- **AND** the server then closes the connection and exits with exit code 0

### Requirement: A failed start is reported as a failure

When the server cannot start, it SHALL log the reason as an error, and the process SHALL exit with a non-zero exit code as soon as the start has failed. It SHALL NOT report that it is up and running, and it SHALL NOT wait for a start timeout before it exits.

#### Scenario: TCP port is in use

- **WHEN** the server is started on a TCP address and port that another process is already listening on
- **THEN** the log contains an error that names the address that could not be bound
- **AND** the log does not state that the server is up and running
- **AND** the process exits with a non-zero exit code without waiting for a start timeout

### Requirement: stdio mode needs a stdin it can watch

In stdio mode, the server SHALL check at start that its stdin is open and can be watched for input, as a pipe or a socket can. If it cannot, the start SHALL fail as a failed start, with an error stating that stdio mode needs such a stdin. A pipe whose writing end is already closed is a valid stdin and ends the server normally.

#### Scenario: stdin is /dev/null

- **WHEN** the server is started in stdio mode with `/dev/null` as stdin
- **THEN** the start fails with an error stating that stdio mode needs a stdin that can be watched, such as a pipe
- **AND** the process exits with a non-zero exit code instead of waiting for input

#### Scenario: stdin is a regular file

- **WHEN** the server is started in stdio mode with a regular file as stdin
- **THEN** the start fails with the same error
- **AND** the process exits with a non-zero exit code

#### Scenario: stdin is a pipe that is already closed

- **WHEN** the server is started in stdio mode with a pipe on stdin whose writing end is already closed
- **THEN** the server starts, sees the end of its input and exits with exit code 0

### Requirement: The server works with every supported Robot Framework version

The server SHALL start, import libraries and run their keywords with every Robot Framework version from the minimum that its package declares.

#### Scenario: Oldest supported Robot Framework version

- **WHEN** the server runs with the oldest Robot Framework version that its package declares
- **AND** a client imports a library whose keywords have arguments with and without default values
- **THEN** the server starts and the import succeeds
- **AND** the library definition marks exactly the arguments that have a default value as having one
- **AND** the client can run the library's keywords

### Requirement: The error of a failed keyword has the message of a local keyword

When a keyword that the server runs fails, the server SHALL report it with the message that Robot Framework shows for the same failure of a local keyword. It SHALL send the whole message, however long: what a report shows is up to the Robot Framework run that called the keyword.

#### Scenario: Keyword raises a ValueError

- **WHEN** a keyword raises `ValueError("bad value")`
- **THEN** the server reports the failure with the message `ValueError: bad value`

#### Scenario: Keyword fails an assertion

- **WHEN** a keyword raises `AssertionError("boom")`
- **THEN** the server reports the failure with the message `boom`

#### Scenario: Keyword fails with a long message

- **WHEN** a keyword fails with a message of 100 lines
- **THEN** the server reports the failure with all 100 lines

### Requirement: The error of a failed keyword names its type and carries its traceback

When a keyword that the server runs fails, the server SHALL report the name of the exception's type and its traceback, which shows the frames of the library code.

#### Scenario: Type and traceback of a failure

- **WHEN** a keyword raises `ValueError("bad value")`
- **THEN** the server reports the type `ValueError`
- **AND** a traceback that contains the line of the library that raised the error

### Requirement: The error of a failed keyword carries its failure mode

When a keyword that the server runs skips the test, fails continuably or fails fatally, as Robot Framework decides it for a local keyword, the server SHALL report the failure mode `SKIP`, `CONTINUABLE` or `FATAL`. Any other failure SHALL carry no failure mode.

#### Scenario: Skip

- **WHEN** a keyword raises `SkipExecution`
- **THEN** the server reports the failure mode `SKIP`

#### Scenario: Continuable failure

- **WHEN** a keyword raises `ContinuableFailure`
- **THEN** the server reports the failure mode `CONTINUABLE`

#### Scenario: Fatal failure

- **WHEN** a keyword raises `FatalError`
- **THEN** the server reports the failure mode `FATAL`

#### Scenario: Normal failure

- **WHEN** a keyword raises `ValueError`
- **THEN** the server reports no failure mode

### Requirement: A fatal failure of a keyword does not stop the server

A fatal failure of a keyword SHALL end only that keyword call. The server SHALL keep running and SHALL run the keywords of later calls, from the same client and from others.

#### Scenario: Keyword call after a fatal failure

- **WHEN** a keyword fails fatally
- **AND** a client then calls a keyword of the server
- **THEN** the server runs that keyword and returns its result

### Requirement: Log messages are forwarded from the client's log level on

The server SHALL forward the log messages that a library logs while it runs a keyword for a client, if their level is at or above the log level that the client reported, DEBUG and TRACE included, and SHALL NOT forward messages below it. A client that has reported no log level gets the messages from INFO on.

#### Scenario: Client at DEBUG

- **WHEN** a client reported the log level `DEBUG` and a keyword logs a DEBUG and a TRACE message
- **THEN** the server forwards the DEBUG message
- **AND** it does not forward the TRACE message

#### Scenario: Client changes its log level

- **WHEN** a client reported the log level `INFO` and later reports `TRACE`
- **AND** a keyword then logs a TRACE message
- **THEN** the server forwards the TRACE message

#### Scenario: Client without a log level

- **WHEN** a client reported no log level and a keyword logs a DEBUG and an INFO message
- **THEN** the server forwards only the INFO message

#### Scenario: Traceback of a failure

- **WHEN** a client reported the log level `DEBUG` and a keyword fails
- **THEN** the server reports the traceback in the error of the keyword call
- **AND** it does not forward the traceback as a log message

### Requirement: What the server prints does not depend on the log level of a client

The server SHALL print its log messages to stderr according to its own options, whatever log level a client reported.

#### Scenario: Library logs for a client at DEBUG

- **WHEN** a client reported the log level `DEBUG` and a library logs a DEBUG message with Python's `logging`
- **THEN** the server forwards the message to the client
- **AND** it does not print the message to stderr

### Requirement: A call before the handshake is answered with NOT_INITIALIZED

The server SHALL answer a request to import a library or to run a keyword that arrives before it has received both `robot/initialize` and `robot/initialized` with a JSON-RPC error with the code `NOT_INITIALIZED` (`-32000`).

#### Scenario: Keyword call before the handshake

- **WHEN** a client sends `robot/run_keyword` before `robot/initialize`
- **THEN** the response is a JSON-RPC error with the code `-32000`

#### Scenario: Library import before the end of the handshake

- **WHEN** a client sends `robot/initialize` and then `robot/import_library` without `robot/initialized`
- **THEN** the response is a JSON-RPC error with the code `-32000`

### Requirement: A call of an unknown keyword is answered with KEYWORD_NOT_FOUND

When a client calls a keyword that the imported library does not have, the server SHALL answer with a JSON-RPC error with the code `KEYWORD_NOT_FOUND` (`-32001`) and a message that names the keyword and the library by its real name, not by its import token.

#### Scenario: Keyword does not exist

- **WHEN** a client calls the keyword `Does Not Exist` of the imported library `MyLibrary`
- **THEN** the response is a JSON-RPC error with the code `-32001` and the message `Keyword 'Does Not Exist' not found in library 'MyLibrary'.`

### Requirement: A refused library import is answered with INVALID_PARAMS

When the server refuses to import a library because it does not serve it, or because the request names no library and the server has no default library, it SHALL answer with a JSON-RPC error with the code `INVALID_PARAMS` (`-32602`) and a message that says why. It SHALL NOT log this as an error.

#### Scenario: Library that the server does not serve

- **WHEN** the server serves only `MyLibrary` and a client imports `OtherLibrary`
- **THEN** the response is a JSON-RPC error with the code `-32602` and the message `Library 'OtherLibrary' is not available.`
- **AND** the server logs no error

#### Scenario: Import without a name

- **WHEN** the server was started without libraries and a client imports a library with an empty name
- **THEN** the response is a JSON-RPC error with the code `-32602` and a message that says that the name is needed
- **AND** the server logs no error

### Requirement: A library that fails to import is reported with Robot Framework's message

When a library fails to import on the server, the server SHALL answer with a JSON-RPC error whose message is the one that Robot Framework shows for a local library, with the traceback of the library's code and the module search path, and without frames of the server's own code.

#### Scenario: Library with a missing dependency

- **WHEN** a client imports a library whose module imports a module that does not exist
- **THEN** the response is a JSON-RPC error whose message names the missing module, the line of the library that imports it and the module search path
- **AND** neither the message nor the data of the response holds a frame of the server's own code

#### Scenario: Library whose initialization fails

- **WHEN** a client imports a library whose `__init__` raises `ValueError("cannot start")`
- **THEN** the response is a JSON-RPC error whose message holds `ValueError: cannot start` and the line of the library that raises it

### Requirement: A keyword error reports only a keyword that ran and failed

The server SHALL answer a keyword call with a `RunKeywordError` only if the keyword ran and failed. It SHALL answer a call that it cannot run or complete for another reason with a JSON-RPC error whose message says why.

#### Scenario: Unknown library token

- **WHEN** a client calls a keyword with a library token that the server does not know
- **THEN** the response is a JSON-RPC error whose message names the token
- **AND** no keyword runs

#### Scenario: Server is stopping

- **WHEN** a keyword call waits for the runner when the stop begins, or arrives after it began
- **THEN** the response is a JSON-RPC error with the message `server is shutting down`

#### Scenario: Return value that cannot be transferred

- **WHEN** a keyword returns a value that cannot be transferred to the client
- **THEN** the response is a JSON-RPC error whose message says why

#### Scenario: Wrong number of arguments

- **WHEN** a client calls a keyword with the wrong number of arguments
- **THEN** the response is a `RunKeywordResult` whose `RunKeywordError` has the message of Robot Framework, as for a local keyword

### Requirement: Error responses carry a traceback only with the server's option

By default, the error responses of the server SHALL carry no traceback, and the server SHALL log the traceback of an unexpected exception. With the option `--send-tracebacks`, the error response for an unexpected exception SHALL also carry its traceback in `data`.

#### Scenario: Server without the option

- **WHEN** the server runs without `--send-tracebacks` and a client calls a keyword with an unknown library token
- **THEN** the JSON-RPC error has no data
- **AND** the server logs the traceback at ERROR level

#### Scenario: Server with the option

- **WHEN** the server runs with `--send-tracebacks` and a client calls a keyword with an unknown library token
- **THEN** the data of the JSON-RPC error holds the traceback
- **AND** the server logs the traceback at ERROR level

### Requirement: JSON values from a client keep their nesting

The server SHALL accept arguments of a library import and of a keyword that hold lists and objects nested to any depth, and SHALL hand them to the library unchanged.

#### Scenario: Argument of a library import

- **WHEN** a client imports a library with the argument `[{"id": 1}]`
- **THEN** the library gets a list with the dict `{"id": 1}`

#### Scenario: Named argument of a library import

- **WHEN** a client imports a library with the named argument `value` set to `{"a": [1, 2]}`, and the library's `__init__` has the type hint `dict` for it
- **THEN** the library gets that dict for `value`

#### Scenario: Argument of a keyword

- **WHEN** a client calls a keyword with the argument `{"a": [1, 2]}` as plain JSON
- **THEN** the keyword gets that dict

#### Scenario: Boolean as an argument of a keyword

- **WHEN** a client calls a keyword with the argument `true`
- **THEN** the keyword gets the boolean `True`, not a number

### Requirement: Strings from a client reach the library unchanged

The server SHALL hand strings from a client to the library as the client sent them, in keyword calls and in library imports, and SHALL NOT resolve variables or escapes in them. The client has already resolved them. The server SHALL still let Robot Framework convert an argument by the signature of the keyword or of the library's `__init__`, as for a local library.

#### Scenario: Backslashes in an argument of a keyword

- **WHEN** a client calls a keyword with the string `C:\temp\new`, `\d+` or `end\`
- **THEN** the keyword gets exactly that string

#### Scenario: Syntax of a variable in an argument of a keyword

- **WHEN** a client calls a keyword with the string `${amount}`, `@{items}`, `&{map}`, `%{PATH}` or `${{1+1}}`
- **THEN** the keyword gets exactly that string
- **AND** the server does not look it up or evaluate it

#### Scenario: Equals sign in an argument of a keyword

- **WHEN** a client calls a keyword that has an argument `value` with the positional string `value=1`
- **THEN** the keyword gets `value=1` as the value of that positional argument

#### Scenario: Strings inside a list or a dict

- **WHEN** a client calls a keyword with a list or a dict that holds the strings `C:\temp` and `${amount}`
- **THEN** the keyword gets a list or a dict that holds exactly these strings

#### Scenario: Named value of a keyword

- **WHEN** a client calls a keyword with a named argument whose value is `C:\temp\new` or `${amount}`
- **THEN** the keyword gets exactly that string for it

#### Scenario: Name of a named argument of a keyword

- **WHEN** a client calls a keyword that takes `**kwargs` with a named argument called `a\b`, `${key}` or `a=b`
- **THEN** the keyword gets a named argument with exactly that name

#### Scenario: Argument of a library import

- **WHEN** a client imports a library with the positional string `C:\temp\new` or `${amount}`
- **THEN** the `__init__` of the library gets exactly that string

#### Scenario: Equals sign in an argument of a library import

- **WHEN** a client imports a library whose `__init__` takes `**kwargs` with the positional string `key=value`
- **THEN** the `__init__` of the library gets `key=value` as a positional value, not as a named argument

#### Scenario: Named value of a library import

- **WHEN** a client imports a library with a named argument whose value is `C:\temp\new` or `${amount}`
- **THEN** the `__init__` of the library gets exactly that string for it

#### Scenario: Name of a named argument of a library import

- **WHEN** a client imports a library whose `__init__` takes `**kwargs` with a named argument called `a\b`, `${key}` or `a=b`
- **THEN** the `__init__` of the library gets a named argument with exactly that name

#### Scenario: String for an argument with a list as its default

- **WHEN** a client calls a keyword whose argument has the default `[1, 2]`, with the string `[3, 4]`
- **THEN** the keyword gets the list `[3, 4]`

#### Scenario: String for an argument with an Enum member as its default

- **WHEN** a client calls a keyword whose argument has a member of an `Enum` as its default, with the string `RIGHT`
- **THEN** the keyword gets the member `RIGHT` of that `Enum`

### Requirement: Keywords that look for control words in their arguments still find them

The server SHALL hand the words `AND`, `ELSE`, `ELSE IF`, `AS` and `WITH NAME` from a client to a keyword as they are, so that a keyword that looks for them in its arguments behaves as in a local call.

#### Scenario: Run Keywords

- **WHEN** a client calls `Run Keywords` of the library `BuiltIn` with the arguments `Log`, `a`, `AND`, `Log` and `b`
- **THEN** the two `Log` keywords run

#### Scenario: Run Keyword If

- **WHEN** a client calls `Run Keyword If` of the library `BuiltIn` with a false condition, a keyword, `ELSE` and a second keyword
- **THEN** the second keyword runs

#### Scenario: Control word as a plain value

- **WHEN** a client calls a keyword with the string `AND` or `ELSE`
- **THEN** the keyword gets exactly that string

### Requirement: A library is imported by the name that the client sent

The server SHALL NOT resolve variables or escapes in the name of a library from a client, so that a client can import a library by a path that holds backslashes or the syntax of a variable.

#### Scenario: Path with the syntax of a variable

- **WHEN** a client imports a library from a file in a directory named `${folder}`, from a server without an allowlist
- **THEN** the import succeeds, and the client gets the definition of the library

#### Scenario: Path with a backslash

- **WHEN** a client imports a library from a path that holds a backslash, from a server without an allowlist
- **THEN** the import succeeds, and the client gets the definition of the library

### Requirement: A keyword with embedded arguments is called by the name from its definition

The server SHALL run a keyword with embedded arguments when a client calls it by the name from the library definition, with the values of the embedded arguments first in the positional arguments. A suite calls such a keyword as it calls a local one.

#### Scenario: Value of an embedded argument

- **WHEN** a library has the keyword `Add ${count} Items`, and a client calls `Add ${count} Items` with the argument `3`
- **THEN** the keyword runs with `3` for `count`

#### Scenario: Call from a suite

- **WHEN** a suite calls `Add 3 Items` of a remote library that has the keyword `Add ${count} Items`
- **THEN** the keyword runs with `3` for `count`, as for a local library

#### Scenario: Value that is not a string

- **WHEN** a client calls `Add ${count} Items` with the argument `[1, 2]`
- **THEN** the keyword gets the list `[1, 2]` for `count`

#### Scenario: Value with backslashes or the syntax of a variable

- **WHEN** a client calls `Add ${count} Items` with the argument `C:\temp` or `${amount}`
- **THEN** the keyword gets exactly that string for `count`

#### Scenario: Further arguments

- **WHEN** a library has the keyword `Copy ${name} To` with a further argument `target`, and a client calls it with the values `a` and `b`, or with `a` and the named argument `target=b`
- **THEN** the keyword runs with `a` for `name` and `b` for `target`

#### Scenario: Embedded argument with a type and its own pattern

- **WHEN** a library has the keyword `Wait ${seconds:\d+} Seconds` whose argument has the type `int`, and a client calls it by that name with the argument `5`
- **THEN** the keyword gets the integer `5`

#### Scenario: Name that also fits other keywords

- **WHEN** a library has the keywords `Do ${what}`, `${who} Now` and `Do ${what} Now`, and a client calls `Do ${what} Now`
- **THEN** the keyword `Do ${what} Now` runs

#### Scenario: Name with the values filled in

- **WHEN** a library `MyLibrary` has the keyword `Add ${count} Items`, and a client calls `Add 3 Items`
- **THEN** the response is a JSON-RPC error with the code `-32001` and the message `Keyword 'Add 3 Items' not found in library 'MyLibrary'.`

### Requirement: The server leaves the console to the client

The server SHALL leave `console` out of the `robot/log` notifications for the log messages that it forwards from Robot Framework, so that the client handles them as messages of a local library.

#### Scenario: Keyword logs a warning

- **WHEN** a keyword logs a warning on the server
- **THEN** the `robot/log` notification has no `console`

#### Scenario: Keyword logs an info message

- **WHEN** a keyword logs a message at level INFO on the server
- **THEN** the `robot/log` notification has no `console`

### Requirement: Argument defaults in a library definition are JSON scalars or text

In a library definition, the server SHALL send an argument default that is `null`, a string, a boolean or a finite number as that value, and any other default as a string with the text that Libdoc shows for it. The import SHALL succeed whatever the defaults of the library are, and a keyword called without such an argument SHALL run with its real default.

#### Scenario: Defaults that are JSON scalars

- **WHEN** a client imports a library with a keyword whose defaults are `None`, `"x"`, `True`, `5` and `1.5`
- **THEN** the definition carries the defaults `null`, `"x"`, `true`, `5` and `1.5`

#### Scenario: A list and a dict as defaults

- **WHEN** a client imports a library with a keyword whose defaults are `[1, 2]` and `{"a": 2}`
- **THEN** the definition carries the strings `"[1, 2]"` and `"{'a': 2}"`

#### Scenario: Enum members as defaults

- **WHEN** a client imports a library with a keyword whose defaults are the member `LEFT` of an `Enum` and the member `RED` of an `IntEnum`
- **THEN** the definition carries the strings `"LEFT"` and `"RED"`

#### Scenario: A default that cannot be pickled

- **WHEN** a client imports a library with a keyword whose default is a lambda
- **THEN** the import succeeds
- **AND** the definition carries a string for that default that starts with `<function`

#### Scenario: Floats that JSON cannot carry

- **WHEN** a client imports a library with a keyword whose defaults are an infinite float and NaN
- **THEN** the definition carries the strings `"inf"` and `"nan"`

#### Scenario: A keyword called without the argument

- **WHEN** a keyword has the default `lambda: 1` for its argument `f` and returns `f()`
- **AND** a client calls the keyword without `f`
- **THEN** the call returns `1`

### Requirement: The library definition carries the name of the library

The server SHALL put the name of the library into its definition, as Robot Framework names the library when it is imported without an alias, and not the token of the import.

#### Scenario: Library imported by its name

- **WHEN** a client imports the library `EndToEndLib`
- **THEN** the name in the definition is `EndToEndLib`
- **AND** the token of the import differs from it

#### Scenario: Library imported from a path

- **WHEN** a client imports a library from the file `PathLib.py` by its path
- **THEN** the name in the definition is `PathLib`

#### Scenario: Two imports of one library

- **WHEN** two clients import the same library
- **THEN** both definitions carry the same name
- **AND** the two tokens differ

### Requirement: The libraries of a client that disconnects are finalized

When a client disconnects, the server SHALL finalize every library that it imported for that client, also a library whose import was still running when the client disconnected. Such a library SHALL be finalized once its import has completed.

#### Scenario: Disconnect after the import

- **WHEN** a client imports a library and disconnects without finalizing it
- **THEN** the server finalizes the library once

#### Scenario: Disconnect while the import runs

- **WHEN** a client disconnects while the server imports a library for it
- **THEN** the server finalizes the library once the import has completed

#### Scenario: Disconnect while the import runs, with another library

- **WHEN** a client has imported one library and disconnects while the server imports a second one for it
- **THEN** the server finalizes both libraries, each once

### Requirement: Library imports leave no messages behind in the server

The server SHALL NOT keep the messages that Robot Framework logs for a library import once the import has completed, so that the memory of the server does not grow with each session.

#### Scenario: Many sessions in a row

- **WHEN** clients import and finalize a library 100 times in a row
- **THEN** the server keeps none of the messages that Robot Framework logged for these imports
