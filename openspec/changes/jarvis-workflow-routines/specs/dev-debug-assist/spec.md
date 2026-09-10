## Purpose

Given an error message or stack trace plus optional hint files, reads the relevant source, traces the failure, and proposes a targeted fix so the user can debug without manually gathering context.

## ADDED Requirements

### Requirement: Error And Hint Intake
The system SHALL accept an error message or stack trace and an optional set of hint locations (files or areas) to focus the investigation.

#### Scenario: Error with hint files
- **WHEN** the user pastes an error and names files or areas to check (for example "the auth middleware and recent changes")
- **THEN** the system SHALL treat the named locations as the primary investigation targets

#### Scenario: Error without hints
- **WHEN** the user pastes an error with no hint locations
- **THEN** the system SHALL derive candidate files from the stack trace where available

### Requirement: Relevant File Reading
The system SHALL read the relevant source files needed to understand the failure, using the available filesystem access.

#### Scenario: Read files referenced in the trace
- **WHEN** the stack trace or hints reference specific files
- **THEN** the system SHALL read those files to gather context before proposing a fix

#### Scenario: Referenced file missing
- **WHEN** a referenced file cannot be found or read
- **THEN** the system SHALL note the missing file and continue with the context it can gather

### Requirement: Stack Trace Tracing And Fix Proposal
The system SHALL trace the error through the gathered context and propose a specific, targeted fix rather than generic advice.

#### Scenario: Targeted fix suggested
- **WHEN** enough context has been gathered
- **THEN** the system SHALL identify the likely root cause and describe a concrete change to address it, referencing the relevant file and location

#### Scenario: Insufficient context
- **WHEN** the gathered context is insufficient to determine a fix
- **THEN** the system SHALL state what additional information or files are needed
