# Spec Delta

## ADDED Requirements

### Requirement: The server works with every supported Robot Framework version

The server SHALL start, import libraries and run their keywords with every Robot Framework version from the minimum that its package declares.

#### Scenario: Oldest supported Robot Framework version

- **WHEN** the server runs with the oldest Robot Framework version that its package declares
- **AND** a client imports a library whose keywords have arguments with and without default values
- **THEN** the server starts and the import succeeds
- **AND** the library definition marks exactly the arguments that have a default value as having one
- **AND** the client can run the library's keywords
