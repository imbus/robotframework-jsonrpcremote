# Spec Delta

## ADDED Requirements

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
