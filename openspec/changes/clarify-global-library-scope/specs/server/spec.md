## ADDED Requirements

### Requirement: A GLOBAL library is shared by all clients of a server

A library with the scope `GLOBAL` SHALL have one instance per set of import arguments for the lifetime of the server process. Every import of it with the same arguments, by any client and in any session, SHALL use that instance. A library with the scope `SUITE` or `TEST` SHALL get a new instance for every import.

#### Scenario: Counter in a GLOBAL library over several sessions

- **WHEN** three sessions one after the other import the same `GLOBAL` library and each calls a keyword that counts the calls of its instance
- **THEN** the calls return 1, 2 and 3

#### Scenario: Counter in a SUITE or TEST library over several sessions

- **WHEN** three sessions one after the other import the same `SUITE` library and the same `TEST` library and call their counting keywords
- **THEN** every call returns 1

### Requirement: Finalizing a GLOBAL library for one client leaves it to the others

When one client's import of a `GLOBAL` library is finalized, the server SHALL keep the shared instance and the library's listeners for the other clients. The server SHALL close the library's listeners only when it stops on SIGTERM or SIGINT, calling their `close` method once.

#### Scenario: One client finalizes while another uses the library

- **WHEN** two clients import the same `GLOBAL` library, which has a listener of its own
- **AND** the session of the first client ends, which finalizes its import
- **THEN** the next call of the second client returns the next count of the same instance
- **AND** the library's listener receives the events of that call
- **AND** the listener's `close` method has not been called

#### Scenario: The server stops

- **WHEN** the server stops on SIGTERM after clients used a `GLOBAL` library whose listener has a `close` method, while one of them is still connected
- **THEN** the listener's `close` method is called once
