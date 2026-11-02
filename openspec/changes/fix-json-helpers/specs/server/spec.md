# Spec Delta

## ADDED Requirements

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
