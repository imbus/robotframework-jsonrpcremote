# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
