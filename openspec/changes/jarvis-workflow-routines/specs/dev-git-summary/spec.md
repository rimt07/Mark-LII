## Purpose

Lets the user get a spoken/written summary of git commit activity over a time window (for example "yesterday") so they can report progress at standup without reading raw git logs.

## ADDED Requirements

### Requirement: Voice-Activated Commit Summary
The system SHALL expose a commit-summary intent through the existing voice activation and tool-dispatch pipeline, recognizing requests such as "summarize my commits from yesterday".

#### Scenario: Voice request routes to the summary intent
- **WHEN** the user asks the assistant to summarize recent git commits by voice or text
- **THEN** the system invokes the commit-summary routine through the existing dispatch without requiring a separate command-line entry point

### Requirement: Time Window Resolution
The system SHALL accept a natural-language time window and resolve it to a concrete date/time range for the commit query.

#### Scenario: Relative window "yesterday"
- **WHEN** the user requests commits from "yesterday"
- **THEN** the system resolves the range to the previous calendar day in the local timezone and queries commits authored within that range

#### Scenario: Default window when unspecified
- **WHEN** the user requests a commit summary without stating a time window
- **THEN** the system SHALL default to the last 24 hours and state the window it used in the response

### Requirement: Commit Retrieval Scope
The system SHALL retrieve commits from the active repository, and MAY be scoped to the current user's authored commits when requested.

#### Scenario: Repository resolved from working directory
- **WHEN** the summary routine runs
- **THEN** the system SHALL retrieve commits from the git repository containing the current working directory

#### Scenario: Not a git repository
- **WHEN** the current working directory is not inside a git repository
- **THEN** the system SHALL return a spoken explanation that no repository was found instead of failing

### Requirement: Key-Change Summarization
The system SHALL produce a human-readable summary that highlights the key changes across the retrieved commits, not merely a list of commit subjects.

#### Scenario: Summary highlights themes
- **WHEN** multiple commits are retrieved for the window
- **THEN** the system SHALL group related changes and describe the key work performed in natural language

#### Scenario: No commits in window
- **WHEN** no commits exist in the resolved window
- **THEN** the system SHALL report that no commits were found for that window
