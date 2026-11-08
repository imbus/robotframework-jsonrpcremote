# Spec Delta

## ADDED Requirements

### Requirement: The command of a pipe or stdio URI can be a list

`uri` SHALL also take a list for a `pipe:` or `stdio:` URI with a command. Its first element SHALL be the scheme, alone or in front of the program, and the other elements SHALL be the further arguments. The client SHALL start the server with these arguments as they are, without splitting or unquoting them, on every platform. It SHALL turn an element that is not a string into a string. A string `uri` SHALL keep its meaning.

#### Scenario: The scheme as an element of its own

- **WHEN** a suite imports a library with `uri=${SERVER}`, where `@{SERVER}` is `pipe:` followed by a list variable with the program of our server and its arguments
- **THEN** the client starts that program with those arguments and `--pipe=<address>`, and keywords run and return their results

#### Scenario: The scheme in front of the program

- **WHEN** the first element of the list is `pipe:` directly followed by the program, as in `pipe:robot-jsonrpcremote-server`
- **THEN** the client starts that program with the other elements as its arguments, as for the scheme as an element of its own

#### Scenario: A stdio command as a list

- **WHEN** the first element of the list is `stdio:`, and the other elements are the program of our server, its arguments and `--stdio`
- **THEN** the client starts the server with those arguments and talks to it over its stdin and stdout

#### Scenario: An argument with a space, a quote or a backslash

- **WHEN** an element of the list holds a space, a quote or a backslash, such as the path of a program in a folder with a space
- **THEN** the server gets it as one argument, unchanged, on Linux, macOS and Windows

#### Scenario: An element that is not a string

- **WHEN** an element of the list is a number, such as `${8271}`
- **THEN** the server gets it as the string `8271`

#### Scenario: A string that looks like a list

- **WHEN** `uri` is the string `['pipe:', 'server']`
- **THEN** the client takes it as a string URI, and the import fails with the error for an unsupported scheme

### Requirement: A list URI is named as the string that it stands for

The client SHALL name a URI that was given as a list in its messages by its string form: the scheme followed by the command, with each argument quoted as a POSIX shell needs it. That string, given as `uri`, SHALL start the server with the same arguments.

#### Scenario: A lost connection

- **WHEN** the server of a list URI exits with exit code 3 during a keyword call
- **THEN** the call fails with the lost-connection error, which names the URI as `pipe:` followed by the command, as in `Connection to 'pipe:<command>' was lost while running keyword '<name>'`, and the exit code

#### Scenario: An argument that needs quotes

- **WHEN** an element of the list holds a space, as in `my library`
- **THEN** the URI in the messages shows it quoted, as in `'my library'`
- **AND** that string, given as `uri`, starts the server with the same arguments as the list

### Requirement: A list without a command is refused

The client SHALL refuse a list for `uri` that holds no command of a `pipe:` or `stdio:` URI when the library is imported, with an error that says that a list holds the command of a `pipe:` or `stdio:` URI, and it SHALL start no process for it.

#### Scenario: An empty list

- **WHEN** `uri` is an empty list
- **THEN** the import fails with that error

#### Scenario: The scheme alone

- **WHEN** `uri` is a list with the element `pipe:` alone
- **THEN** the import fails with that error, and no process is started

#### Scenario: A URI with two slashes

- **WHEN** the first element of the list is a URI with two slashes, such as `tcp://127.0.0.1:8271`, `pipe://robot` or `stdio://robot-jsonrpcremote-server`
- **THEN** the import fails with that error, and no process is started

#### Scenario: No supported scheme

- **WHEN** the first element of the list is a program without a scheme, such as `robot-jsonrpcremote-server`
- **THEN** the import fails with that error, and no process is started
