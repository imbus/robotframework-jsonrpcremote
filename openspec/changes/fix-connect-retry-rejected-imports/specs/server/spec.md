## MODIFIED Requirements

### Requirement: Requests that can no longer run are rejected

Requests that need the Robot runner (importing or finalizing a library, running a keyword) and that are still waiting when the stop begins, or arrive afterwards, SHALL NOT be executed. The server SHALL answer them with a JSON-RPC error with the code `SHUTTING_DOWN` (`-32002`) and the message `server is shutting down`. None of them SHALL stay unanswered.

#### Scenario: Keyword call is waiting when the stop begins

- **WHEN** a keyword call is waiting for the runner
- **AND** the stop begins
- **THEN** the call is answered with the code `-32002` and the message `server is shutting down`
- **AND** the keyword is not executed

#### Scenario: Keyword call arrives after the stop began

- **WHEN** the stop has begun
- **AND** a keyword call arrives before the client's connection is closed
- **THEN** the call is answered with the code `-32002` and the message `server is shutting down`
- **AND** the keyword is not executed

#### Scenario: Library import arrives after the stop began

- **WHEN** the stop has begun
- **AND** a library import arrives before the client's connection is closed
- **THEN** the import is answered with the code `-32002` and the message `server is shutting down`
- **AND** the library is not imported
