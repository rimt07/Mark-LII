## Purpose

Scans a source path for TODO/FIXME markers and turns each into a properly formatted Jira ticket, or a dry-run list of proposed tickets when Jira is not configured, so backlog items in code are captured without manual data entry.

## ADDED Requirements

### Requirement: TODO/FIXME Discovery
The system SHALL scan a specified path for developer markers (TODO, FIXME, and equivalent) and extract each marker's text, file path, and line number.

#### Scenario: Scan a directory
- **WHEN** the user asks to find TODO comments in a given path (for example "src/")
- **THEN** the system SHALL search the files under that path and collect every TODO/FIXME occurrence with its location

#### Scenario: No markers found
- **WHEN** the scanned path contains no TODO/FIXME markers
- **THEN** the system SHALL report that none were found and create no tickets

### Requirement: Ticket Formatting
The system SHALL convert each discovered marker into a formatted ticket containing a concise title derived from the marker text and a description including the file path and line number.

#### Scenario: One ticket per marker
- **WHEN** markers are discovered
- **THEN** the system SHALL produce one formatted ticket per marker with title, description, file path, and line reference

### Requirement: Jira Creation With Config Gating
The system SHALL create tickets in Jira only when Jira access is configured, and SHALL degrade gracefully otherwise.

#### Scenario: Jira configured
- **WHEN** Jira access is configured and reachable
- **THEN** the system SHALL create each formatted ticket in Jira and report the created ticket identifiers

#### Scenario: Jira not configured (dry run)
- **WHEN** Jira access is not configured or unreachable
- **THEN** the system SHALL return the list of proposed tickets as a dry-run preview and clearly state that no tickets were created

### Requirement: Duplicate Awareness
The system SHALL avoid creating obvious duplicate tickets within a single scan run.

#### Scenario: Identical markers in one run
- **WHEN** the same marker text and location would produce identical tickets in one run
- **THEN** the system SHALL create at most one ticket for that marker
