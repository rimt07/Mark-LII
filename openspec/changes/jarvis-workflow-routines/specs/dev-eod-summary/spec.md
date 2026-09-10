## Purpose

Generates a readable end-of-day summary of what the user shipped and what remains open, and persists it so the next session can open with an accurate briefing.

## ADDED Requirements

### Requirement: Day Activity Aggregation
The system SHALL aggregate the day's shipped work (commits within the current day) and open items into a single readable summary.

#### Scenario: Summarize today's work
- **WHEN** the user asks for a summary of what they shipped today and what is still open
- **THEN** the system SHALL collect the day's commits and known open items and produce a natural-language summary of both

#### Scenario: Quiet day
- **WHEN** no commits or open items exist for the day
- **THEN** the system SHALL report that there was no recorded activity for the day

### Requirement: Open Item Inclusion
The system SHALL include open items in the summary when such sources are available, and SHALL omit unavailable sources without failing.

#### Scenario: Jira available
- **WHEN** Jira access is configured
- **THEN** the summary SHALL include the user's open Jira tickets

#### Scenario: Open-item source unavailable
- **WHEN** an open-item source (such as Jira) is not configured
- **THEN** the system SHALL produce the summary from available sources and note which sources were unavailable

### Requirement: Persistence For Next Session
The system SHALL persist the generated end-of-day summary to session memory so it can inform the next session's briefing.

#### Scenario: Summary persisted
- **WHEN** an end-of-day summary is generated
- **THEN** the system SHALL store the summary in memory associated with the current date

#### Scenario: Summary recalled next session
- **WHEN** a new session starts after an end-of-day summary was stored
- **THEN** the stored summary SHALL be available for recall as prior context
