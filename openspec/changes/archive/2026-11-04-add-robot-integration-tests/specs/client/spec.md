# Spec Delta

## ADDED Requirements

### Requirement: The source of a remote keyword comes with its line

The client SHALL report the source of a remote keyword to Robot Framework together with the line that the server reports for it, so that what reads the source, such as the spec files of Libdoc and listeners, gets the same as for a local library.

#### Scenario: Source and line

- **WHEN** the server reports the source `/srv/MyLibrary.py` and the line `14` for a keyword
- **THEN** Robot Framework has that source and that line for the keyword

#### Scenario: Spec file of Libdoc

- **WHEN** Libdoc writes a JSON or XML spec file for a remote library whose server reports the lines of its keywords
- **THEN** the spec file holds for each keyword its source and its line

#### Scenario: Source without a line

- **WHEN** the server reports a source and no line for a keyword
- **THEN** Robot Framework has that source and no line for the keyword

#### Scenario: Line without a source

- **WHEN** the server reports a line and no source for a keyword
- **THEN** Robot Framework has no line for the keyword, because it would otherwise pair that line with the source file of the client
