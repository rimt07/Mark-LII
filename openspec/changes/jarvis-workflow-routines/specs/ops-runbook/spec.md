## Purpose

Stores, recalls, and executes named remediation runbooks so the user can reference a known procedure by name (for example "the standard restart runbook") to remediate an incident.

## ADDED Requirements

### Requirement: Runbook Persistence
The system SHALL persist named runbooks, each consisting of an ordered set of remediation steps, in a durable store that survives across sessions.

#### Scenario: Save a runbook
- **WHEN** the user defines or updates a named runbook
- **THEN** the system SHALL persist the runbook so it is available in future sessions

#### Scenario: List runbooks
- **WHEN** the user asks what runbooks exist
- **THEN** the system SHALL list the stored runbook names

### Requirement: Runbook Recall By Name
The system SHALL recall a runbook by its name, tolerating reasonable natural-language variation.

#### Scenario: Reference by name
- **WHEN** the user references a runbook by name (for example "the standard restart runbook")
- **THEN** the system SHALL locate the matching stored runbook

#### Scenario: Unknown runbook
- **WHEN** no stored runbook matches the referenced name
- **THEN** the system SHALL report that the runbook was not found and offer to list available runbooks

### Requirement: Runbook Execution
The system SHALL execute the steps of a recalled runbook and report the outcome of each step.

#### Scenario: Execute steps in order
- **WHEN** the user asks to follow a named runbook
- **THEN** the system SHALL execute its steps in order and report the result of each

#### Scenario: Step failure handling
- **WHEN** a runbook step fails
- **THEN** the system SHALL report the failing step and stop or continue according to the runbook's defined behavior

#### Scenario: Confirmation for irreversible steps
- **WHEN** a runbook step performs an irreversible or destructive action
- **THEN** the system SHALL require confirmation through the existing confirmation gate before executing that step
