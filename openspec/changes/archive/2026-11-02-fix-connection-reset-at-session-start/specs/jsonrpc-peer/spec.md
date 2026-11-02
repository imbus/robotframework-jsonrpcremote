# Spec Delta

## ADDED Requirements

### Requirement: An error that ends the peer is not reported as never retrieved

If reading from the connection fails and nobody waits for the peer's completion, asyncio SHALL NOT report that error as never retrieved. A caller that waits for the completion SHALL still receive the error.

#### Scenario: Nobody waits for the completion

- **WHEN** reading from the connection fails
- **AND** nobody waits for the peer's completion
- **THEN** asyncio reports no exception that was never retrieved

#### Scenario: A caller waits for the completion afterwards

- **WHEN** reading from the connection fails
- **AND** a caller then waits for the peer's completion
- **THEN** the caller receives that error
