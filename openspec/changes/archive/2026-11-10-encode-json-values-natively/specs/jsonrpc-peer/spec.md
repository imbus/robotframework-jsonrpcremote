## MODIFIED Requirements

### Requirement: A response that cannot be written fails only its own request

When the response to a request cannot be written as JSON or exceeds the maximum message size, the peer SHALL log the reason at ERROR level and SHALL answer the request with the code `-32603` and its `id`.

#### Scenario: Result cannot be written as JSON

- **WHEN** the request handler of a request with the `id` `7` returns a value that cannot be written as JSON
- **THEN** the response carries the code `-32603` and the `id` `7`
- **AND** the peer logs an error that holds the reason

#### Scenario: Result holds a float that JSON does not allow

- **WHEN** the request handler of a request with the `id` `7` returns `{"value": float("nan")}`
- **THEN** the response carries the code `-32603` and the `id` `7`
- **AND** the peer writes no message that holds `NaN`

#### Scenario: Response exceeds the maximum message size

- **WHEN** the response to a request with the `id` `7` exceeds the maximum message size of the peer
- **THEN** the response carries the code `-32603` and the `id` `7`
- **AND** the peer logs an error that holds the reason

#### Scenario: Inside a batch

- **WHEN** a batch holds a request with the `id` `1`, whose result can be written, and a request with the `id` `2`, whose result cannot
- **THEN** the answer holds the result for the `id` `1` and an error with the code `-32603` for the `id` `2`
