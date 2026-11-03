# Spec Delta

## ADDED Requirements

### Requirement: Strings from a client reach the library unchanged

The server SHALL hand strings from a client to the library exactly as the client sent them, in keyword calls and in library imports, and SHALL NOT resolve variables or escapes in them. The client has already resolved them.

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
